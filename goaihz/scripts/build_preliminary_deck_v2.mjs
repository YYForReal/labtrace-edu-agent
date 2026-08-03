import fs from "node:fs/promises";
import path from "node:path";

const artifactToolModule = await import(
  process.env.ARTIFACT_TOOL_ENTRY || "@oai/artifact-tool"
);
const { Presentation, PresentationFile } = artifactToolModule;
const sharpModule = await import(process.env.SHARP_ENTRY || "sharp");
const sharp = sharpModule.default ?? sharpModule;

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const GOAIHZ = path.join(ROOT, "goaihz");
const ASSETS = path.join(GOAIHZ, "submission", "assets");
const SUBMISSION = path.join(GOAIHZ, "submission");
const OUT = path.join(GOAIHZ, "tmp", "slides-v2");

const C = {
  paper: "#F6F2E8",
  white: "#FFFDF8",
  ink: "#14231C",
  green: "#163F30",
  dark: "#0F2B22",
  sage: "#DCE8DD",
  sage2: "#BFD3C4",
  orange: "#E96A42",
  orangeSoft: "#F5D7C9",
  muted: "#65736B",
  line: "#C7D0C8",
  grid: "#E4E6DD",
  gold: "#D7B574",
};
const FONT = "FandolHei";

async function readImage(file) {
  const bytes = await fs.readFile(file);
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

async function writeBlob(file, blob) {
  await fs.writeFile(file, new Uint8Array(await blob.arrayBuffer()));
}

function shape(slide, name, position, options = {}) {
  return slide.shapes.add({
    geometry: options.geometry ?? "rect",
    name,
    position,
    fill: options.fill ?? "none",
    line: options.line ?? { style: "solid", fill: "none", width: 0 },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
    ...(options.shadow ? { shadow: options.shadow } : {}),
  });
}

function text(slide, name, value, position, options = {}) {
  const item = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: options.fill ?? "none",
    line: options.line ?? { style: "solid", fill: "none", width: 0 },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
  });
  item.text = value;
  item.text.style = {
    typeface: FONT,
    fontSize: options.fontSize ?? 20,
    color: options.color ?? C.ink,
    bold: options.bold ?? false,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
    autoFit: "shrinkText",
    wrap: "square",
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return item;
}

function rule(slide, name, left, top, width, color = C.line, weight = 1) {
  return shape(
    slide,
    name,
    { left, top, width, height: 0 },
    {
      geometry: "straightConnector1",
      line: { style: "solid", fill: color, width: weight },
    },
  );
}

function image(slide, name, bytes, position, alt, options = {}) {
  if (options.frame !== false) {
    shape(slide, `${name}-frame`, position, {
      geometry: "roundRect",
      fill: options.frameFill ?? C.white,
      line: { style: "solid", fill: options.frameLine ?? C.line, width: 1 },
      borderRadius: "rounded-lg",
      shadow: options.shadow ?? "shadow-sm",
    });
  }
  const inset = options.frame === false ? 0 : 7;
  slide.images.add({
    blob: bytes,
    contentType: "image/png",
    alt,
    fit: options.fit ?? "contain",
    position: {
      left: position.left + inset,
      top: position.top + inset,
      width: position.width - inset * 2,
      height: position.height - inset * 2,
    },
    geometry: options.geometry ?? "rect",
  });
}

function notes(slide, body, sources = []) {
  const sourceBlock = sources.length
    ? `\n\n[Sources]\n${sources.map((item) => `- ${item}`).join("\n")}\n[/Sources]`
    : "";
  slide.speakerNotes.textFrame.setText(`${body}${sourceBlock}`);
  slide.speakerNotes.setVisible(true);
}

function page(presentation, number, title, kicker = "格物智评 LABTRACE") {
  const slide = presentation.slides.add();
  slide.background.fill = C.paper;
  text(slide, `kicker-${number}`, kicker, { left: 54, top: 28, width: 480, height: 22 }, {
    fontSize: 12,
    bold: true,
    color: C.orange,
  });
  text(slide, `page-${number}`, String(number).padStart(2, "0"), {
    left: 1180,
    top: 30,
    width: 48,
    height: 22,
  }, {
    fontSize: 12,
    color: C.muted,
    alignment: "right",
  });
  text(slide, `title-${number}`, title, { left: 54, top: 64, width: 1120, height: 58 }, {
    fontSize: 40,
    bold: true,
    color: C.green,
    verticalAlignment: "middle",
  });
  rule(slide, `top-rule-${number}`, 54, 132, 1172, C.green, 1.2);
  return slide;
}

function label(slide, name, value, left, top, width, options = {}) {
  shape(slide, `${name}-bg`, { left, top, width, height: options.height ?? 32 }, {
    geometry: "roundRect",
    fill: options.fill ?? C.sage,
    line: { style: "solid", fill: options.line ?? "none", width: 0 },
    borderRadius: "rounded-full",
  });
  text(slide, name, value, { left: left + 10, top: top + 2, width: width - 20, height: (options.height ?? 32) - 4 }, {
    fontSize: options.fontSize ?? 14,
    bold: true,
    color: options.color ?? C.green,
    alignment: "center",
    verticalAlignment: "middle",
  });
}

function bigMetric(slide, name, value, caption, left, top, options = {}) {
  text(slide, `${name}-value`, value, { left, top, width: options.width ?? 180, height: 92 }, {
    fontSize: options.fontSize ?? 72,
    bold: true,
    color: options.color ?? C.orange,
    verticalAlignment: "bottom",
  });
  text(slide, `${name}-caption`, caption, { left, top: top + 96, width: options.width ?? 220, height: 48 }, {
    fontSize: 16,
    color: options.captionColor ?? C.muted,
  });
}

function arrow(slide, name, left, top, width) {
  shape(slide, name, { left, top, width, height: 0 }, {
    geometry: "straightConnector1",
    line: {
      style: "solid",
      fill: C.orange,
      width: 2,
      endArrowType: "triangle",
    },
  });
}

async function main() {
  await fs.mkdir(OUT, { recursive: true });
  await fs.mkdir(SUBMISSION, { recursive: true });

  const assets = {
    home: await readImage(path.join(ASSETS, "labtrace-home-v2.png")),
    allergenResult: await readImage(path.join(ASSETS, "labtrace-allergen-result-v2.png")),
    gameResult: await readImage(path.join(ASSETS, "labtrace-game-result-v2.png")),
    diagnosis: await readImage(path.join(ASSETS, "labtrace-diagnosis-v2.png")),
    allergenCover: await readImage(path.join(ASSETS, "report-allergen-cover.png")),
    allergenEvidence: await readImage(path.join(ASSETS, "report-allergen-evidence.png")),
    gameCover: await readImage(path.join(ASSETS, "report-game-cover.png")),
    gameEvidence: await readImage(path.join(ASSETS, "report-game-evidence.png")),
  };

  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  deck.theme.colorScheme = {
    name: "LabTrace Evidence Dossier",
    themeColors: {
      accent1: C.green,
      accent2: C.orange,
      accent3: C.sage2,
      accent4: C.gold,
      accent5: C.orangeSoft,
      accent6: C.muted,
      bg1: C.paper,
      bg2: C.white,
      tx1: C.ink,
      tx2: C.muted,
      dk1: C.dark,
      dk2: C.green,
      lt1: C.white,
      lt2: C.sage,
      hlink: C.orange,
      folHlink: C.gold,
    },
  };

  // 1 — Cover: editorial dossier, not a dashboard.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.dark;
    shape(slide, "cover-band", { left: 0, top: 0, width: 22, height: 720 }, {
      fill: C.orange,
      line: { style: "solid", fill: C.orange, width: 0 },
    });
    text(slide, "cover-kicker", "GOAI 2026 · AI+教育 · 初赛方案", {
      left: 60,
      top: 44,
      width: 520,
      height: 30,
    }, { fontSize: 16, bold: true, color: C.orangeSoft });
    text(slide, "cover-title", "格物智评\nLabTrace", {
      left: 58,
      top: 126,
      width: 550,
      height: 208,
    }, { fontSize: 68, bold: true, color: C.white, verticalAlignment: "bottom" });
    text(slide, "cover-subtitle", "高校实验报告证据化批改 Agent", {
      left: 62,
      top: 350,
      width: 520,
      height: 46,
    }, { fontSize: 27, color: C.sage });
    rule(slide, "cover-rule", 62, 430, 480, C.orange, 2);
    text(slide, "cover-promise", "让每一分回到证据\n让每次批改进入教学闭环", {
      left: 62,
      top: 468,
      width: 450,
      height: 100,
    }, { fontSize: 27, bold: true, color: C.white });
    text(slide, "cover-team", "单人队伍：独立变量", {
      left: 62,
      top: 642,
      width: 300,
      height: 26,
    }, { fontSize: 15, color: C.sage2 });
    image(slide, "cover-allergen", assets.allergenCover, {
      left: 690,
      top: 74,
      width: 226,
      height: 542,
    }, "完全合成的过敏原 ELISA 教学实验报告封面", {
      frameFill: C.white,
      frameLine: C.sage2,
      shadow: "shadow-md",
    });
    image(slide, "cover-game", assets.gameCover, {
      left: 948,
      top: 104,
      width: 226,
      height: 542,
    }, "按真实课程任务结构合成重构的游戏开发实验报告封面", {
      frameFill: C.white,
      frameLine: C.orange,
      shadow: "shadow-md",
    });
    label(slide, "cover-tag", "跨课程 · 可复核 · 可复现", 742, 650, 382, {
      fill: C.orange,
      color: C.white,
      height: 34,
    });
    notes(slide, "开场：LabTrace 面向高校教师，不替教师发布成绩，而是把证据定位、逐项建议和批改回写串成可终审的任务闭环。", [
      "goaihz/docs/product.md",
      "goaihz/docs/closed_loop_demo_plan.md",
    ]);
  }

  // 2 — Real problem signal.
  {
    const slide = page(deck, 2, "真实课程材料暴露的，不是“生成评语”问题", "SCENE VALUE · 真实需求");
    bigMetric(slide, "corpus", "57", "份游戏开发课程实验报告\n用于内部需求观察（不公开原文）", 62, 172, {
      width: 260,
      fontSize: 92,
    });
    rule(slide, "problem-v", 352, 168, 0, C.line, 1);
    const items = [
      ["01", "证据散落", "正文、表格、运行截图和参数记录分散；教师需要反复定位。"],
      ["02", "标准漂移", "相同问题跨报告重复判断，课程 rubric 难以稳定落实。"],
      ["03", "结果难沉淀", "批改结束后只留下分数，无法支持讲评与下一轮教学。"],
    ];
    items.forEach(([no, title, body], index) => {
      const y = 170 + index * 150;
      text(slide, `problem-no-${index}`, no, { left: 400, top: y, width: 52, height: 36 }, {
        fontSize: 17,
        bold: true,
        color: C.orange,
      });
      text(slide, `problem-title-${index}`, title, { left: 468, top: y - 4, width: 250, height: 44 }, {
        fontSize: 28,
        bold: true,
        color: C.green,
      });
      text(slide, `problem-body-${index}`, body, { left: 730, top: y, width: 460, height: 70 }, {
        fontSize: 18,
        color: C.muted,
      });
      if (index < items.length - 1) rule(slide, `problem-rule-${index}`, 400, y + 106, 790);
    });
    label(slide, "problem-scope", "结论：需要“证据—判断—复核—教学反馈”的闭环 Agent", 390, 618, 700, {
      fill: C.green,
      color: C.white,
      height: 40,
      fontSize: 17,
    });
    notes(slide, "57 是本地课程材料目录的报告数量，仅用于汇总需求观察。本项目不公开、训练或展示其中任何学生原文、截图、身份、教师或院校信息。", [
      "本地内部目录：2026年《计算机游戏设计》实验报告（汇总计数 57）",
      "goaihz/docs/compliance.md",
    ]);
  }

  // 3 — Task loop.
  {
    const slide = page(deck, 3, "Agent 的价值，是完成一条教师可接管的任务链", "AGENT LOOP · 六步闭环");
    const steps = [
      ["01", "理解任务", "课程要求\nrubric 版本"],
      ["02", "解析证据", "正文 / 表格\n图片 / 参数"],
      ["03", "逐项判断", "理由绑定\n证据定位"],
      ["04", "确定校验", "分值范围\n引用关系"],
      ["05", "教师终审", "确认 / 调整\n保留原建议"],
      ["06", "教学诊断", "只聚合\n已复核结果"],
    ];
    steps.forEach(([no, title, body], index) => {
      const x = 58 + index * 199;
      text(slide, `loop-no-${index}`, no, { left: x, top: 190, width: 48, height: 30 }, {
        fontSize: 15,
        bold: true,
        color: C.orange,
      });
      shape(slide, `loop-dot-${index}`, { left: x, top: 242, width: 24, height: 24 }, {
        geometry: "ellipse",
        fill: index === 4 ? C.orange : C.green,
        line: { style: "solid", fill: "none", width: 0 },
      });
      if (index < steps.length - 1) arrow(slide, `loop-arrow-${index}`, x + 34, 254, 152);
      text(slide, `loop-title-${index}`, title, { left: x, top: 300, width: 155, height: 42 }, {
        fontSize: 23,
        bold: true,
        color: C.green,
      });
      text(slide, `loop-body-${index}`, body, { left: x, top: 354, width: 155, height: 66 }, {
        fontSize: 17,
        color: C.muted,
      });
    });
    text(slide, "loop-contract", "GradeTrace 是贯穿全链路的证据账本", {
      left: 84,
      top: 500,
      width: 520,
      height: 50,
    }, { fontSize: 30, bold: true, color: C.ink });
    text(slide, "loop-contract-detail", "分项得分 + 理由 + evidence_id + 置信度 + 教师事件", {
      left: 84,
      top: 562,
      width: 650,
      height: 38,
    }, { fontSize: 19, color: C.muted });
    label(slide, "loop-boundary", "低置信度不会自动发布", 848, 510, 300, {
      fill: C.orangeSoft,
      color: C.orange,
      height: 46,
      fontSize: 18,
    });
    notes(slide, "六步闭环把 Agent 判断与教师最终裁量分开。确定性校验阻止分数越界、总分不一致和未知证据引用进入复核界面。", [
      "goaihz/src/labtrace/contracts.py",
      "goaihz/docs/architecture.md",
    ]);
  }

  // 4 — Cross-domain proof.
  {
    const slide = page(deck, 4, "同一闭环，跨越两种完全不同的实验证据", "GENERALITY · 双案例");
    image(slide, "cross-allergen", assets.allergenEvidence, {
      left: 72,
      top: 164,
      width: 250,
      height: 430,
    }, "过敏原 ELISA 合成实验的数据页");
    image(slide, "cross-game", assets.gameEvidence, {
      left: 366,
      top: 164,
      width: 250,
      height: 430,
    }, "游戏开发合成重构实验的运行证据页");
    text(slide, "cross-eq", "≠", { left: 654, top: 264, width: 90, height: 80 }, {
      fontSize: 58,
      bold: true,
      color: C.orange,
      alignment: "center",
    });
    text(slide, "cross-title", "不是课程专用打分器", {
      left: 768,
      top: 178,
      width: 400,
      height: 60,
    }, { fontSize: 32, bold: true, color: C.green });
    text(slide, "cross-body", "生命科学关注对照、重复性和检测边界；游戏开发关注组件参数、运行日志和边界测试。\n\nAgent 复用的是证据契约、教师复核和交付闭环，而不是一套僵硬关键词。", {
      left: 770,
      top: 266,
      width: 400,
      height: 200,
    }, { fontSize: 21, color: C.muted });
    label(slide, "cross-allergen-label", "过敏原教学案例 · 建议 68", 74, 614, 246, {
      fill: C.sage,
      color: C.green,
    });
    label(slide, "cross-game-label", "游戏开发案例 · 建议 75", 368, 614, 246, {
      fill: C.orangeSoft,
      color: C.orange,
    });
    label(slide, "cross-disclosure", "全部公开内容均无真实学生身份与原文", 770, 526, 380, {
      fill: C.green,
      color: C.white,
      height: 42,
    });
    notes(slide, "过敏原报告为完全合成教学材料且明确不作医学诊断。游戏开发报告只参考实际课程常见任务结构重新编写，不复用学生原文、截图、代码仓库或元数据。", [
      "goaihz/data/synthetic/demo-allergen-001_实验报告.docx",
      "goaihz/data/synthetic/demo-game-dev-001_实验报告.docx",
      "goaihz/docs/compliance.md",
    ]);
  }

  // 5 — Product view.
  {
    const slide = page(deck, 5, "评委打开网页即可切换案例并运行完整闭环", "PRODUCT EXPERIENCE · 可运行 Demo");
    image(slide, "home-ui", assets.home, {
      left: 52,
      top: 154,
      width: 844,
      height: 484,
    }, "LabTrace 浏览器版首页和三个匿名案例", {
      fit: "cover",
      frameLine: C.green,
      shadow: "shadow-md",
    });
    text(slide, "home-side-title", "三分钟内可验证", {
      left: 950,
      top: 176,
      width: 250,
      height: 50,
    }, { fontSize: 30, bold: true, color: C.green });
    const checks = [
      "选择合成案例",
      "生成逐项证据链",
      "教师调整并确认",
      "下载 Word / JSON",
      "查看学情并删除",
    ];
    checks.forEach((item, index) => {
      text(slide, `home-check-${index}`, `0${index + 1}`, {
        left: 950,
        top: 254 + index * 66,
        width: 36,
        height: 28,
      }, { fontSize: 14, bold: true, color: C.orange });
      text(slide, `home-check-text-${index}`, item, {
        left: 1000,
        top: 248 + index * 66,
        width: 210,
        height: 40,
      }, { fontSize: 19, bold: true, color: C.ink });
    });
    label(slide, "home-url", "yywebsite.cn/education/", 950, 596, 250, {
      fill: C.green,
      color: C.white,
      height: 40,
    });
    notes(slide, "公开浏览器版无需登录或模型密钥。页面同时保留规则模式披露，避免把确定性演示伪装成大模型推理。", [
      "frontend/src/views/LabTraceDemoView.vue",
      "goaihz/api.py",
    ]);
  }

  // 6 — Allergen evidence.
  {
    const slide = page(deck, 6, "过敏原案例：证据充分，也必须看见“不能下结论”", "CASE A · 生命科学");
    image(slide, "allergen-doc", assets.allergenEvidence, {
      left: 56,
      top: 152,
      width: 292,
      height: 504,
    }, "过敏原 ELISA 报告的数据、表格与标准曲线");
    image(slide, "allergen-ui", assets.allergenResult, {
      left: 386,
      top: 164,
      width: 618,
      height: 348,
    }, "过敏原案例 68 分的证据化评分界面", {
      fit: "cover",
      frameLine: C.green,
    });
    bigMetric(slide, "allergen-score", "68", "建议分 / 100", 1048, 172, {
      width: 150,
      fontSize: 76,
    });
    bigMetric(slide, "allergen-confidence", "62%", "分析维度置信度\n触发教师终审", 1048, 364, {
      width: 160,
      fontSize: 50,
      color: C.green,
    });
    text(slide, "allergen-why", "Agent 找到了对照、双复孔和标准曲线，也明确指出：缺少变异系数、回收率、异常值和检出限讨论。", {
      left: 402,
      top: 550,
      width: 592,
      height: 84,
    }, { fontSize: 20, color: C.muted });
    label(slide, "allergen-boundary", "教学检测 ≠ 医疗诊断", 1032, 576, 188, {
      fill: C.orangeSoft,
      color: C.orange,
      height: 38,
    });
    notes(slide, "案例建议总分 68。分析维度置信度 0.62，因缺少定量误差和异常值验证而进入教师终审。公开数据完全合成，不对应患者或食品安全结论。", [
      "goaihz/demo_engine.py",
      "goaihz/data/synthetic/demo-allergen-001_实验报告.docx",
    ]);
  }

  // 7 — Game evidence.
  {
    const slide = page(deck, 7, "游戏开发案例：运行成功，不等于验证充分", "CASE B · 游戏开发");
    image(slide, "game-doc", assets.gameEvidence, {
      left: 56,
      top: 152,
      width: 292,
      height: 504,
    }, "游戏开发实验的测试数据和运行证据重构图");
    image(slide, "game-ui", assets.gameResult, {
      left: 386,
      top: 164,
      width: 618,
      height: 348,
    }, "游戏开发案例 75 分的证据化评分界面", {
      fit: "cover",
      frameLine: C.orange,
    });
    bigMetric(slide, "game-score", "75", "建议分 / 100", 1048, 172, {
      width: 150,
      fontSize: 76,
    });
    bigMetric(slide, "game-confidence", "66%", "分析维度置信度\n触发教师终审", 1048, 364, {
      width: 160,
      fontSize: 50,
      color: C.green,
    });
    text(slide, "game-why", "Agent 识别 Rigidbody、Continuous、事件日志与三次运行；仍要求补充帧率、极端速度、边缘碰撞和连续重置测试。", {
      left: 402,
      top: 550,
      width: 592,
      height: 84,
    }, { fontSize: 20, color: C.muted });
    label(slide, "game-boundary", "运行截图 ≠ 充分验证", 1024, 576, 206, {
      fill: C.orangeSoft,
      color: C.orange,
      height: 38,
    });
    notes(slide, "案例建议总分 75。分析维度置信度 0.66，Agent 能理解游戏实验常见组件和运行证据，但不会把三次成功运行直接等同于稳定性结论。", [
      "goaihz/demo_engine.py",
      "goaihz/data/synthetic/demo-game-dev-001_实验报告.docx",
    ]);
  }

  // 8 — Human review.
  {
    const slide = page(deck, 8, "教师终审不是免责声明，而是产品中的强制状态", "HUMAN-IN-THE-LOOP · 可审计");
    image(slide, "review-ui", assets.allergenResult, {
      left: 54,
      top: 156,
      width: 736,
      height: 414,
    }, "低置信度证据和教师终审控件", {
      fit: "cover",
      frameLine: C.green,
      shadow: "shadow-md",
    });
    text(slide, "review-flow", "68", { left: 846, top: 180, width: 130, height: 90 }, {
      fontSize: 72,
      bold: true,
      color: C.muted,
      alignment: "center",
    });
    arrow(slide, "review-arrow", 972, 232, 92);
    text(slide, "review-final", "70", { left: 1060, top: 180, width: 130, height: 90 }, {
      fontSize: 72,
      bold: true,
      color: C.orange,
      alignment: "center",
    });
    text(slide, "review-caption", "模型建议\n完整保留", {
      left: 850,
      top: 292,
      width: 130,
      height: 60,
    }, { fontSize: 18, color: C.muted, alignment: "center" });
    text(slide, "review-caption2", "教师调整\n形成最终分", {
      left: 1056,
      top: 292,
      width: 140,
      height: 60,
    }, { fontSize: 18, color: C.muted, alignment: "center" });
    const audit = [
      "调整前分项与理由",
      "教师说明与最终分",
      "证据引用与置信度",
      "Word 批注 + trace JSON",
    ];
    audit.forEach((item, index) => {
      text(slide, `audit-${index}`, `✓  ${item}`, {
        left: 850,
        top: 396 + index * 48,
        width: 340,
        height: 34,
      }, { fontSize: 19, color: index === 3 ? C.green : C.ink, bold: index === 3 });
    });
    label(slide, "review-rule", "未终审，不进入正式成绩与班级统计", 818, 612, 390, {
      fill: C.green,
      color: C.white,
      height: 42,
    });
    notes(slide, "演示中教师将分析维度从 8 调整为 10，总分从 68 变为 70。系统保留 suggested_trace，复核结果写入独立 review 事件。", [
      "goaihz/api.py",
      "goaihz/src/labtrace/contracts.py",
    ]);
  }

  // 9 — Diagnosis.
  {
    const slide = page(deck, 9, "批改的终点不是分数，而是下一次教学动作", "LEARNING DIAGNOSIS · 已复核数据");
    image(slide, "diagnosis-ui", assets.diagnosis, {
      left: 54,
      top: 156,
      width: 790,
      height: 444,
    }, "仅聚合已复核记录的班级学情诊断", {
      fit: "cover",
      frameLine: C.green,
      shadow: "shadow-md",
    });
    bigMetric(slide, "diag-count", "4", "已复核样本", 916, 166, {
      width: 120,
      fontSize: 58,
      color: C.green,
    });
    bigMetric(slide, "diag-average", "73.5", "班级均分", 1060, 166, {
      width: 150,
      fontSize: 58,
    });
    bigMetric(slide, "diag-rate", "53%", "最弱维度达成率", 916, 352, {
      width: 240,
      fontSize: 58,
      color: C.green,
    });
    text(slide, "diag-action", "建议教学动作：\n用同一组数据示范“描述结果、解释原因、验证结论、讨论误差”的差异。", {
      left: 916,
      top: 506,
      width: 296,
      height: 104,
    }, { fontSize: 18, color: C.muted });
    notes(slide, "诊断只聚合 approved/adjusted 的分项成绩，不把未复核建议直接转化为学生画像。当前 4 条演示记录的最弱维度为分析、验证与误差讨论。", [
      "goaihz/src/labtrace/diagnosis.py",
      "goaihz/data/synthetic/grade_records.json",
    ]);
  }

  // 10 — Engineering and safety.
  {
    const slide = page(deck, 10, "可复现工程：把安全、降级和容量写进默认配置", "ENGINEERING · 生产基线");
    const nodes = [
      ["浏览器", "Vue 3\n/education/"],
      ["API", "FastAPI\n限流 / 校验"],
      ["Agent", "解析工具\nGradeTrace"],
      ["教师", "终审事件\nWord / JSON"],
    ];
    nodes.forEach(([title, body], index) => {
      const x = 64 + index * 286;
      shape(slide, `arch-node-${index}`, { left: x, top: 190, width: 224, height: 126 }, {
        geometry: "roundRect",
        fill: index === 2 ? C.green : C.white,
        line: { style: "solid", fill: index === 2 ? C.green : C.line, width: 1 },
        borderRadius: "rounded-lg",
      });
      text(slide, `arch-title-${index}`, title, { left: x + 18, top: 210, width: 188, height: 32 }, {
        fontSize: 21,
        bold: true,
        color: index === 2 ? C.white : C.green,
        alignment: "center",
      });
      text(slide, `arch-body-${index}`, body, { left: x + 18, top: 254, width: 188, height: 48 }, {
        fontSize: 16,
        color: index === 2 ? C.sage : C.muted,
        alignment: "center",
      });
      if (index < nodes.length - 1) arrow(slide, `arch-arrow-${index}`, x + 232, 253, 42);
    });
    const facts = [
      ["1 GiB", "容器内存上限"],
      ["2", "并发评分上限"],
      ["24 h", "默认自动删除"],
      ["25 MiB", "单文件上传上限"],
      ["11", "闭环与安全测试"],
      ["0", "公开 Demo 所需密钥"],
    ];
    facts.forEach(([value, caption], index) => {
      const col = index % 3;
      const row = Math.floor(index / 3);
      const x = 86 + col * 390;
      const y = 402 + row * 108;
      text(slide, `fact-v-${index}`, value, { left: x, top: y, width: 120, height: 56 }, {
        fontSize: 36,
        bold: true,
        color: index === 4 ? C.orange : C.green,
      });
      text(slide, `fact-c-${index}`, caption, { left: x + 132, top: y + 10, width: 210, height: 36 }, {
        fontSize: 17,
        color: C.muted,
      });
    });
    label(slide, "arch-prod", "非 root · 只读根文件系统 · 立即删除 · 浏览器不见绝对路径", 266, 628, 750, {
      fill: C.dark,
      color: C.white,
      height: 40,
      fontSize: 16,
    });
    notes(slide, "本地前端生产构建峰值约 795 MiB；生产机 2 核、3.8 GiB 内存，应用实测空闲约 116 MiB、完成一次 DOCX 后约 162 MiB。前端在本地构建，容器限制 1 GiB。", [
      "goaihz/docs/deployment_runbook.md",
      "goaihz/Dockerfile.production",
      "goaihz/docker-compose.production.yml",
      "goaihz/tests/test_competition_profile.py",
    ]);
  }

  // 11 — Roadmap and close.
  {
    const slide = deck.slides.add();
    slide.background.fill = C.dark;
    shape(slide, "close-band", { left: 0, top: 0, width: 22, height: 720 }, {
      fill: C.orange,
      line: { style: "solid", fill: C.orange, width: 0 },
    });
    text(slide, "close-kicker", "独立变量 · GOAI 2026 AI+教育", {
      left: 60,
      top: 42,
      width: 480,
      height: 28,
    }, { fontSize: 16, bold: true, color: C.orangeSoft });
    text(slide, "close-title", "先把每一分\n讲清楚", {
      left: 60,
      top: 136,
      width: 530,
      height: 200,
    }, { fontSize: 68, bold: true, color: C.white });
    text(slide, "close-body", "初赛：双案例公开闭环 + 生产部署\n复赛：真实模型适配 + 批量持久化 + 教师金标评测\n决赛：权限审计 + 失败演练 + 现场答辩", {
      left: 64,
      top: 390,
      width: 590,
      height: 150,
    }, { fontSize: 22, color: C.sage });
    rule(slide, "close-rule", 64, 582, 540, C.orange, 2);
    text(slide, "close-url", "https://yywebsite.cn/education/", {
      left: 64,
      top: 616,
      width: 500,
      height: 36,
    }, { fontSize: 20, bold: true, color: C.white });
    shape(slide, "close-sheet", { left: 746, top: 90, width: 420, height: 536 }, {
      geometry: "roundRect",
      fill: C.white,
      line: { style: "solid", fill: C.white, width: 0 },
      borderRadius: "rounded-lg",
      shadow: "shadow-md",
    });
    text(slide, "close-sheet-title", "提交物已经形成同一证据包", {
      left: 788,
      top: 140,
      width: 334,
      height: 72,
    }, { fontSize: 30, bold: true, color: C.green });
    const outputs = [
      "可运行浏览器 Demo",
      "PPTX / PDF 方案材料",
      "自然语音字幕视频",
      "双案例合成报告",
      "运行与部署说明",
      "测试、合规与开源边界",
    ];
    outputs.forEach((item, index) => {
      text(slide, `close-output-${index}`, `0${index + 1}`, {
        left: 790,
        top: 248 + index * 50,
        width: 36,
        height: 28,
      }, { fontSize: 13, bold: true, color: C.orange });
      text(slide, `close-output-text-${index}`, item, {
        left: 842,
        top: 242 + index * 50,
        width: 260,
        height: 34,
      }, { fontSize: 18, color: C.ink });
    });
    label(slide, "close-tag", "可追溯 · 可复核 · 可复现 · 可迁移", 790, 566, 330, {
      fill: C.green,
      color: C.white,
      height: 38,
    });
    notes(slide, "收束：初赛先证明真实闭环和工程可行性；复赛再用经授权金标评测真实模型、批量任务和教师效率，不把计划项包装成已实现。", [
      "goaihz/docs/engineering_plan_v1.md",
      "goaihz/submission/初赛提交清单.md",
    ]);
  }

  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    await writeBlob(
      path.join(OUT, `${stem}.png`),
      await deck.export({ slide, format: "png", scale: 1 }),
    );
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(OUT, `${stem}.layout.json`), await layout.text());
  }

  const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
  await writeBlob(path.join(OUT, "deck-montage.webp"), montage);

  const thumbnails = [];
  const thumbW = 384;
  const thumbH = 216;
  for (let index = 0; index < deck.slides.items.length; index += 1) {
    thumbnails.push({
      input: await sharp(path.join(OUT, `slide-${String(index + 1).padStart(2, "0")}.png`))
        .resize(thumbW, thumbH, { fit: "fill" })
        .png()
        .toBuffer(),
      left: 24 + (index % 3) * (thumbW + 18),
      top: 24 + Math.floor(index / 3) * (thumbH + 18),
    });
  }
  await sharp({
    create: {
      width: 24 * 2 + 3 * thumbW + 2 * 18,
      height: 24 * 2 + 4 * thumbH + 3 * 18,
      channels: 4,
      background: C.paper,
    },
  })
    .composite(thumbnails)
    .png()
    .toFile(path.join(OUT, "deck-montage.png"));

  const pptx = await PresentationFile.exportPptx(deck);
  const output = path.join(SUBMISSION, "格物智评_LabTrace_GOAI初赛方案.pptx");
  await pptx.save(output);
  try {
    await fs.rename(`${output}.inspect.ndjson`, path.join(OUT, "deck.inspect.ndjson"));
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
