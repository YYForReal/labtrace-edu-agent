"""
Tool Registry — 工具注册与执行

将 Claude 的 tool_use 请求路由到对应的 Python 函数执行，
桥接 Agent 的 Tool Call 与现有 agent_skills 脚本。
"""

import json
import os
import sys
import traceback
import logging
from typing import Any, Callable, Optional

# 确保 agent_skills 脚本可被 import
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册中心。

    每个 Tool 对应一个 Python 函数，输入为 dict（Claude 传入的 tool input），
    输出为 JSON-serializable 的 dict 或 str（作为 tool_result 返回给 Claude）。
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._tools: dict[str, Callable] = {}
        self._register_builtin_tools()

    def register(self, name: str, func: Callable):
        """手动注册一个工具"""
        self._tools[name] = func

    async def execute(self, name: str, inputs: dict) -> dict | str:
        """
        执行工具。

        Args:
            name: 工具名称
            inputs: Claude 传入的工具参数

        Returns:
            工具执行结果（JSON-serializable）
        """
        if name not in self._tools:
            return {
                "error": f"未注册的工具: {name}",
                "available": list(self._tools.keys()),
            }

        try:
            func = self._tools[name]
            import asyncio
            import inspect

            if inspect.iscoroutinefunction(func):
                result = await func(inputs)
            else:
                # 同步函数在线程池中执行，避免阻塞事件循环
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, func, inputs)

            return result

        except Exception as e:
            return {
                "error": str(e),
                "traceback": traceback.format_exc(),
                "tool": name,
            }

    def list_tools(self) -> list[str]:
        """列出所有已注册的工具"""
        return list(self._tools.keys())

    # ─── 内置工具注册 ────────────────────────────────────────────

    def _register_builtin_tools(self):
        """注册内置的 7 个批改工具"""
        self.register("parse_document", self._tool_parse_document)
        self.register("validate_scores", self._tool_validate_scores)
        self.register("generate_feedback", self._tool_generate_feedback)
        self.register("inject_grading_to_docx", self._tool_inject_grading)
        self.register("fill_excel_scores", self._tool_fill_excel)
        self.register("analyze_video", self._tool_analyze_video)
        self.register("request_human_review", self._tool_request_human_review)

    # ─── Tool 实现：桥接到 agent_skills 脚本 ──────────────────────

    # tool result 最大字符数（超过此值会截断）
    # MiniMax M3 上下文最高 1M tokens，预留 system+history 空间
    TOOL_RESULT_MAX_CHARS = 80_000  # ~40K tokens，安全上限

    def _tool_parse_document(self, inputs: dict) -> dict:
        """
        解析学生文档 → 调用 agent_skills/doc-parser/scripts/parse_docx.py

        当 extract_images=True 时，会提取文档中嵌入的图片为 base64 编码，
        返回 images_for_vision 字段供 Agent 发送给 LLM Vision API 进行多模态分析。

        注意：MiniMax-M3（Anthropic 兼容 API）支持 image/video 类型输入，
        因此图片 base64 在 M3 端点与原生 Anthropic 端点都有意义。
        对于 M2.x 等不支持图片的端点，建议改用独立 VisionService 处理。
        """
        file_path = inputs["file_path"]
        extract_images = inputs.get("extract_images", True)

        if not os.path.exists(file_path):
            return {"error": f"文件不存在: {file_path}"}

        ext = os.path.splitext(file_path)[1].lower()

        # .doc 先转换为 .docx
        if ext == ".doc":
            from agent_skills.doc_parser.scripts.convert_doc import convert_doc_to_docx

            docx_path = convert_doc_to_docx(file_path)
            if not docx_path:
                return {
                    "error": f".doc 转换失败: {file_path}，请确保 LibreOffice 已安装"
                }
            file_path = docx_path

        # 解析 DOCX
        if ext in (".docx", ".doc"):
            from agent_skills.doc_parser.scripts.parse_docx import parse_docx

            result = parse_docx(file_path)
        elif ext == ".pdf":
            # PDF 优先尝试 pdf2docx 转换为 DOCX 再解析（保留图片/表格等结构）
            pdf_converted = False
            try:
                from pdf2docx import Converter
                import tempfile

                docx_path = tempfile.mktemp(suffix=".docx")
                cv = Converter(file_path)
                cv.convert(docx_path)
                cv.close()
                file_path = docx_path
                pdf_converted = True
                from agent_skills.doc_parser.scripts.parse_docx import parse_docx

                result = parse_docx(file_path)
                result["metadata"]["pdf_converted"] = True
                result["metadata"]["original_pdf"] = os.path.basename(
                    inputs["file_path"]
                )
            except Exception as e:
                logger.info(
                    "PDF 转 DOCX 失败 (%s)，回退到 pdfplumber 直接解析: %s",
                    file_path,
                    e,
                )
                from agent_skills.doc_parser.scripts.parse_pdf import parse_pdf

                result = parse_pdf(inputs["file_path"])
        else:
            return {"error": f"不支持的文件格式: {ext}，支持 .doc/.docx/.pdf"}

        # 提取学生信息
        from agent_skills.doc_parser.scripts.extract_student_info import (
            extract_student_info,
        )

        student_info = extract_student_info(os.path.basename(file_path))
        if student_info:
            result["student_info"] = student_info

        # 面向通用课程的文档证据画像：让 Agent 在评分前知道这是一份
        # 纯文本、图文混排、表格/数据型还是代码/截图型报告。
        result["document_profile"] = self._build_document_profile(
            result,
            original_file_path=inputs["file_path"],
            normalized_file_path=file_path,
        )

        # 处理图片：如果提取了 base64 图片，构建 vision 格式供 Agent 使用
        if extract_images and result.get("images"):
            vision_images = []
            for img in result["images"]:
                if img.get("base64") and img.get("media_type"):
                    vision_images.append(
                        {
                            "index": img["index"],
                            "base64": img["base64"],
                            "media_type": img["media_type"],
                            "size_bytes": img.get("size_bytes", 0),
                            "context": img.get("context", ""),
                            "paragraph_index": img.get("paragraph_index"),
                            "docx_paragraph_index": img.get("docx_paragraph_index"),
                        }
                    )
            if vision_images:
                result["images_for_vision"] = vision_images
                result["instruction"] = (
                    f"文档包含 {len(vision_images)} 张可分析的图片。"
                    "图片 base64 数据已附在 images_for_vision 字段中，"
                    "请使用 Vision 能力分析图片内容（如代码、软件操作、实验结果、"
                    "图表/数据表、游戏界面等），并据此评估学生的实践成果。"
                )

        # ── 始终移除 images 列表中的 base64（只保留在 images_for_vision 中） ──
        if result.get("images"):
            for img in result["images"]:
                img.pop("base64", None)

        # ── 截断保护：确保 tool result 不会撑爆上下文窗口 ──
        result = self._truncate_parse_result(result)

        return result

    @staticmethod
    def _build_document_profile(
        result: dict,
        *,
        original_file_path: str,
        normalized_file_path: str,
    ) -> dict:
        """
        构建供 LLM 快速理解材料类型的轻量画像。

        该画像不替代 full_text / tables / images，只用于减少 Agent 在
        不同课程材料之间的误判：例如 Word 图文实验报告没有视频时，
        不应套用游戏开发课程的扣分逻辑。
        """
        metadata = result.get("metadata") or {}
        paragraphs = result.get("paragraphs") or []
        tables = result.get("tables") or []
        images = result.get("images") or []
        full_text = result.get("full_text") or ""

        table_count = metadata.get("table_count", len(tables))
        image_count = metadata.get("image_count", len(images))
        text_length = metadata.get("word_count", len(full_text))
        placeholder_count = result.get("image_placeholder_count", image_count)

        original_ext = os.path.splitext(original_file_path)[1].lower().lstrip(".")
        normalized_ext = os.path.splitext(normalized_file_path)[1].lower().lstrip(".")

        if image_count and table_count:
            modality = "图文表格混排报告"
        elif image_count:
            modality = "图文混排报告"
        elif table_count:
            modality = "表格/数据型报告"
        else:
            modality = "纯文本报告"

        lower_text = full_text.lower()
        software_keywords = [
            "unity",
            "c#",
            "python",
            "matlab",
            "spss",
            "excel",
            "solidworks",
            "proteus",
            "multisim",
            "jupyter",
            "仿真",
            "实验数据",
            "误差",
            "结果分析",
            "运行结果",
            "流程图",
        ]
        detected_keywords = []
        for keyword in software_keywords:
            if keyword in lower_text or keyword in full_text:
                detected_keywords.append(keyword)

        hints = [
            "先按 rubric 判断课程目标和评分维度，不要套用固定课程模板。",
            "如评分标准未要求视频，不要因为未提交视频而扣分。",
        ]
        if image_count:
            hints.append(
                "图片描述应作为证据使用，但需要结合图片附近正文判断其所属步骤或结果。"
            )
        if table_count:
            hints.append(
                "表格和数据可能是实验报告的核心证据，应纳入结果分析和结论判断。"
            )
        if detected_keywords:
            hints.append(
                "检测到课程/软件关键词，可用于辅助判断材料类型，但最终以 rubric 为准。"
            )

        return {
            "original_file_type": original_ext or result.get("file_type", ""),
            "normalized_file_type": normalized_ext or result.get("file_type", ""),
            "file_type": result.get("file_type", normalized_ext or original_ext),
            "modality": modality,
            "text_length": text_length,
            "paragraph_count": len(paragraphs),
            "table_count": table_count,
            "image_count": image_count,
            "image_placeholder_count": placeholder_count,
            "converted": original_ext != normalized_ext,
            "detected_keywords": detected_keywords[:12],
            "grading_hints": hints,
        }

    def _truncate_parse_result(self, result: dict) -> dict:
        """
        截断过大的文档解析结果，确保序列化后不超过上下文安全上限。

        截断策略（按优先级依次执行）：
        1. 移除 xml_analysis（非核心信息）
        2. 精简 paragraphs 列表（只保留标题和前后若干段）
        3. 截断 full_text（保留前后各部分）
        4. 精简 tables（只保留摘要，丢弃详细数据）
        """
        import json as _json

        def _estimate_size(d):
            return len(_json.dumps(d, ensure_ascii=False, default=str))

        size = _estimate_size(result)
        if size <= self.TOOL_RESULT_MAX_CHARS:
            return result

        # 策略 1：移除 xml_analysis
        result.pop("xml_analysis", None)
        size = _estimate_size(result)
        if size <= self.TOOL_RESULT_MAX_CHARS:
            return result

        # 策略 2：精简 paragraphs —— 保留所有标题和前 10 + 后 5 个正文段落
        paragraphs = result.get("paragraphs", [])
        if len(paragraphs) > 30:
            headings = [p for p in paragraphs if p.get("level") is not None]
            body = [p for p in paragraphs if p.get("level") is None]
            if len(body) > 15:
                kept_body = (
                    body[:10]
                    + [
                        {
                            "text": f"... (省略 {len(body)-15} 个段落) ...",
                            "style": "Normal",
                            "level": None,
                        }
                    ]
                    + body[-5:]
                )
            else:
                kept_body = body
            result["paragraphs"] = headings + kept_body

        size = _estimate_size(result)
        if size <= self.TOOL_RESULT_MAX_CHARS:
            return result

        # 策略 3：截断 full_text（保留前 6000 + 后 2000 字符）
        full_text = result.get("full_text", "")
        max_text = 8000
        if len(full_text) > max_text:
            front = max_text * 3 // 4  # 6000
            back = max_text - front  # 2000
            omitted = len(full_text) - front - back
            result["full_text"] = (
                full_text[:front]
                + f"\n\n[... 省略中间 {omitted} 字符 ...]\n\n"
                + full_text[-back:]
            )
            result["_full_text_truncated"] = True
            result["_original_text_length"] = len(full_text)

        size = _estimate_size(result)
        if size <= self.TOOL_RESULT_MAX_CHARS:
            return result

        # 策略 4：精简表格 —— 只保留摘要和前 3 行数据
        tables = result.get("tables", [])
        for tbl in tables:
            data = tbl.get("data", [])
            if len(data) > 5:
                tbl["data"] = data[:3] + [[f"... (共 {len(data)} 行)"]]
                tbl["_truncated"] = True

        size = _estimate_size(result)
        if size <= self.TOOL_RESULT_MAX_CHARS:
            return result

        # 最终兜底：如果还是太大，移除 images 描述信息
        result.pop("images", None)
        result["_note"] = "文档内容已截断以适应上下文窗口限制"

        return result

    def _tool_validate_scores(self, inputs: dict) -> dict:
        """
        评分校验 → 调用 agent_skills/grading-engine/scripts/validate_scores.py
        """
        from agent_skills.grading_engine.scripts.validate_scores import validate_scores

        grading_result = inputs["grading_result"]
        rubric_id = inputs.get("rubric_id", "")

        # 加载评分标准获取 max_score
        rubrics_dir = self.config.get(
            "rubrics_dir",
            os.path.join(_PROJECT_ROOT, "config", "rubrics"),
        )
        rubric_path = os.path.join(rubrics_dir, f"{rubric_id}.json")

        rubric = {}
        if os.path.exists(rubric_path):
            with open(rubric_path, "r", encoding="utf-8") as f:
                rubric = json.load(f)

        return validate_scores(grading_result, rubric)

    def _tool_generate_feedback(self, inputs: dict) -> dict:
        """
        评语生成 → 调用 agent_skills/feedback-generator/scripts/comment_templates.py
        提供预设评语词库，Claude 自己组合生成最终评语。
        """
        from agent_skills.feedback_generator.scripts.comment_templates import (
            get_templates,
        )

        grading_result = inputs["grading_result"]
        style = inputs.get("style", "standard")
        total_score = grading_result.get("total_score", 0)

        templates = get_templates(style, total_score)

        return {
            "templates": templates,
            "grading_summary": {
                "total_score": total_score,
                "strengths": grading_result.get("strengths", []),
                "weaknesses": grading_result.get("weaknesses", []),
                "suggestions": grading_result.get("suggestions", []),
            },
            "instruction": (
                "请根据以上评分信息和预设评语模板，"
                "生成 150-200 字的个性化评语，遵循三明治法则。"
            ),
        }

    def _tool_inject_grading(self, inputs: dict) -> dict:
        """
        批改结果注入 DOCX → 调用 agent_skills/report-injector/scripts/inject_grading_to_docx.py

        注意：
        1. inject_all 签名是 (input_path, output_path, config)，不要搞反参数顺序
        2. 如果输入文件是 .doc 格式，需要先转换为 .docx 再注入
        3. 如果 grading_config 中没有 signature 配置，自动加载 config/signature.json 的默认签名
        """
        from agent_skills.report_injector.scripts.inject_grading_to_docx import (
            inject_all,
        )

        input_docx = inputs["input_docx"]
        grading_config = inputs["grading_config"]
        output_path = inputs.get("output_path")

        # 鲁棒性处理：LLM 有时会将 grading_config 传为 JSON 字符串而非对象
        if isinstance(grading_config, str):
            try:
                grading_config = json.loads(grading_config)
            except (json.JSONDecodeError, TypeError):
                return {
                    "error": f"grading_config 格式错误：应为 JSON 对象，收到字符串无法解析"
                }

        if not os.path.exists(input_docx):
            return {"error": f"输入文件不存在: {input_docx}"}

        # .doc 文件需要先转换为 .docx，python-docx 不支持 .doc 格式
        ext = os.path.splitext(input_docx)[1].lower()
        actual_input = input_docx
        if ext == ".doc":
            # 检查是否已有同名 .docx（parse_document 阶段可能已经转换过）
            docx_path = os.path.splitext(input_docx)[0] + ".docx"
            if os.path.exists(docx_path):
                actual_input = docx_path
            else:
                from agent_skills.doc_parser.scripts.convert_doc import (
                    convert_doc_to_docx,
                )

                converted = convert_doc_to_docx(input_docx)
                if not converted:
                    return {
                        "error": f".doc 转换失败: {input_docx}，请确保 LibreOffice 已安装"
                    }
                actual_input = converted

        if not output_path:
            # 输出文件名基于原始输入文件名（保留原始扩展名 .docx）
            base = os.path.splitext(actual_input)[0]
            output_path = f"{base}_批改.docx"

        # ── 自动注入默认签名：如果 grading_config 中没有 signature，加载预设签名配置 ──
        if "signature" not in grading_config or not grading_config.get("signature"):
            sig_config = self._load_default_signature_config()
            if sig_config and sig_config.get("enabled"):
                grading_config["signature"] = {
                    "image_path": sig_config["_abs_image_path"],
                    "width_inches": sig_config.get("width_inches", 1.1),
                    "height_inches": sig_config.get("height_inches", 0.62),
                    "locate_keyword": sig_config.get("locate_keyword", "指导教师签字"),
                    "locate_fallback_keywords": sig_config.get(
                        "locate_fallback_keywords", []
                    ),
                }
                # 同步 author 到 grading_config 顶层（用于批注署名）
                if sig_config.get("author") and "author" not in grading_config:
                    grading_config["author"] = sig_config["author"]

        # ── 校验并修复 annotations 格式 ──
        # LLM 可能发送两种格式：
        #   正确格式：{"text": "...", "target": {"type": "keyword", "keyword": "..."}}
        #   错误格式：{"text": "...", "keyword": "..."}（扁平化，缺少 target 嵌套）
        annotations = grading_config.get("annotations", [])
        if annotations:
            fixed_annotations = []
            for ann in annotations:
                if not isinstance(ann, dict):
                    continue
                if "text" not in ann:
                    continue
                # 已有正确的 target 结构
                if "target" in ann and isinstance(ann["target"], dict):
                    fixed_annotations.append(ann)
                # 扁平化 keyword 格式 → 自动包装为 target
                elif "keyword" in ann:
                    fixed_annotations.append(
                        {
                            "text": ann["text"],
                            "target": {
                                "type": "keyword",
                                "keyword": ann["keyword"],
                            },
                        }
                    )
                # 扁平化 paragraph_index 格式
                elif "paragraph_index" in ann:
                    fixed_annotations.append(
                        {
                            "text": ann["text"],
                            "target": {
                                "type": "paragraph_index",
                                "index": ann["paragraph_index"],
                            },
                        }
                    )
                elif "index" in ann:
                    fixed_annotations.append(
                        {
                            "text": ann["text"],
                            "target": {
                                "type": "paragraph_index",
                                "index": ann["index"],
                            },
                        }
                    )
                else:
                    # 无法修复，跳过该条批注
                    import logging as _logging

                    _logging.getLogger(__name__).warning(
                        "跳过格式异常的批注: %s",
                        json.dumps(ann, ensure_ascii=False)[:200],
                    )
            grading_config["annotations"] = fixed_annotations

        # 注意参数顺序：inject_all(input_path, output_path, config)
        result = inject_all(actual_input, output_path, grading_config)

        return {
            "success": True,
            "output_path": output_path,
            "details": result,
        }

    def _load_default_signature_config(self) -> dict | None:
        """
        加载 config/signature.json 默认签名配置。

        返回的 dict 中额外附加 _abs_image_path 字段（签名图片绝对路径），
        如果签名未启用或图片不存在则返回 None。
        """
        sig_path = os.path.join(_PROJECT_ROOT, "config", "signature.json")
        if not os.path.exists(sig_path):
            return None

        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig_config = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        if not sig_config.get("enabled", True):
            return None

        # 解析签名图片绝对路径
        image_path = sig_config.get("image_path", "")
        if image_path and not os.path.isabs(image_path):
            abs_path = os.path.join(_PROJECT_ROOT, image_path)
        else:
            abs_path = image_path

        if not abs_path or not os.path.exists(abs_path):
            return None

        sig_config["_abs_image_path"] = abs_path
        return sig_config

    def _tool_fill_excel(self, inputs: dict) -> dict:
        """
        成绩回填 Excel → 调用 agent_skills/score-aggregator/scripts/fill_score_to_excel.py
        """
        from agent_skills.score_aggregator.scripts.fill_score_to_excel import (
            fill_scores_to_excel,
        )

        excel_path = inputs["excel_path"]
        scores_data = inputs["scores_data"]
        output_path = inputs.get("output_path")
        fill_mode = inputs.get("fill_mode", "total_score")
        week_number = inputs.get("week_number")

        if not output_path:
            base, ext = os.path.splitext(excel_path)
            output_path = f"{base}_已填{ext}"

        result = fill_scores_to_excel(
            excel_path=excel_path,
            scores_data=scores_data,
            output_path=output_path,
            fill_mode=fill_mode,
            week_number=week_number,
            add_comments=True,
            auto_stats=True,
        )

        return {
            "success": True,
            "output_path": output_path,
            "matched": result.get("matched", 0),
            "comments_added": result.get("comments_added", 0),
            "total_in_excel": result.get("total_in_excel", 0),
        }

    def _tool_analyze_video(self, inputs: dict) -> dict:
        """
        视频分析 → ffmpeg 提取关键帧。

        注意：帧图像文件路径会返回给 Claude，
        后续由 GradingAgent 使用 Vision API 发送图片进行多模态分析。
        """
        from app.agent.video_analyzer import extract_key_frames

        video_path = inputs["video_path"]
        max_frames = inputs.get("max_frames", 8)

        if not os.path.exists(video_path):
            return {"error": f"视频文件不存在: {video_path}"}

        # 提取关键帧
        output_dir = os.path.join(
            os.path.dirname(video_path),
            f"_frames_{os.path.splitext(os.path.basename(video_path))[0]}",
        )
        frames = extract_key_frames(video_path, output_dir, max_frames)

        return {
            "success": True,
            "frames_extracted": len(frames),
            "frame_paths": frames,
            "analysis_focus": inputs.get("analysis_focus", "游戏原型复现"),
            "instruction": (
                "关键帧已提取。请使用 Vision 能力分析这些截图，"
                "评估游戏原型的完成度、界面质量和功能演示情况。"
            ),
        }

    def _tool_request_human_review(self, inputs: dict) -> dict:
        """
        请求人工审核 → 将审核请求入队，等待教师处理。
        """
        student_id = inputs["student_id"]
        student_name = inputs.get("student_name", "")
        reason = inputs["reason"]
        current_result = inputs.get("current_result", {})

        # TODO: 实际应用中，这里会将请求写入数据库/消息队列，
        # 并通过 WebSocket 通知前端。当前 Prototype 版本直接返回确认。
        review_request = {
            "student_id": student_id,
            "student_name": student_name,
            "reason": reason,
            "current_result": current_result,
            "status": "pending_review",
        }

        return {
            "review_submitted": True,
            "message": (
                f"已将学生 {student_name}({student_id}) 的批改结果"
                f"提交人工审核。原因: {reason}"
            ),
            "instruction": (
                "人工审核请求已提交。请暂停对该学生的后续操作，"
                "继续处理其他学生。教师审核完成后会通知系统。"
            ),
        }
