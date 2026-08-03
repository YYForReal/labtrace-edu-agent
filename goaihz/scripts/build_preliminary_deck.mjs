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
const OUT_DIR = path.join(GOAIHZ, "tmp", "slides");
const SUBMISSION_DIR = path.join(GOAIHZ, "submission");

const COLORS = {
  cream: "#F5F0E6",
  paper: "#FFFDF8",
  green: "#183D2D",
  forest: "#0F2D21",
  mint: "#DCE9DF",
  mint2: "#C5D8C8",
  orange: "#EF6A32",
  orangeSoft: "#F8D7C6",
  ink: "#18211C",
  muted: "#667168",
  line: "#C7CEC7",
  white: "#FFFFFF",
  danger: "#B63A2B",
  yellow: "#F0C35A",
};

const FONT = "FandolHei";

async function readImageBlob(imagePath) {
  const bytes = await fs.readFile(imagePath);
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function textbox(slide, name, text, position, options = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: options.fill ?? "none",
    line: options.line ?? { style: "solid", fill: "none", width: 0 },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    fontSize: options.fontSize ?? 20,
    color: options.color ?? COLORS.ink,
    bold: options.bold ?? false,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
    autoFit: options.autoFit ?? "shrinkText",
    wrap: "square",
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return shape;
}

function rect(slide, name, position, options = {}) {
  return slide.shapes.add({
    geometry: options.geometry ?? "roundRect",
    name,
    position,
    fill: options.fill ?? COLORS.paper,
    line: options.line ?? {
      style: "solid",
      fill: options.lineColor ?? COLORS.line,
      width: options.lineWidth ?? 1,
    },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
    ...(options.shadow ? { shadow: options.shadow } : {}),
  });
}

function line(slide, name, position, color = COLORS.line, width = 2) {
  return slide.shapes.add({
    geometry: "straightConnector1",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: color, width },
  });
}

function circle(slide, name, left, top, diameter, fill, label, labelColor = COLORS.white) {
  rect(
    slide,
    name,
    { left, top, width: diameter, height: diameter },
    {
      geometry: "ellipse",
      fill,
      line: { style: "solid", fill, width: 0 },
    },
  );
  textbox(
    slide,
    `${name}-label`,
    label,
    { left, top: top + 1, width: diameter, height: diameter - 2 },
    {
      fontSize: 18,
      bold: true,
      color: labelColor,
      alignment: "center",
      verticalAlignment: "middle",
    },
  );
}

function baseSlide(presentation, title, pageNumber, kicker = "格物智评 LABTRACE") {
  const slide = presentation.slides.add();
  slide.background.fill = COLORS.cream;
  textbox(
    slide,
    `kicker-${pageNumber}`,
    kicker,
    { left: 42, top: 30, width: 270, height: 22 },
    { fontSize: 12, bold: true, color: COLORS.orange },
  );
  textbox(
    slide,
    `title-${pageNumber}`,
    title,
    { left: 42, top: 60, width: 1120, height: 62 },
    { fontSize: 39, bold: true, color: COLORS.green, verticalAlignment: "middle" },
  );
  line(slide, `rule-${pageNumber}`, { left: 42, top: 130, width: 1196, height: 0 }, COLORS.green, 1.5);
  textbox(
    slide,
    `footer-${pageNumber}`,
    String(pageNumber).padStart(2, "0"),
    { left: 1184, top: 668, width: 54, height: 22 },
    { fontSize: 12, color: COLORS.muted, alignment: "right", verticalAlignment: "bottom" },
  );
  return slide;
}

function addPill(slide, name, text, left, top, width, options = {}) {
  rect(
    slide,
    `${name}-bg`,
    { left, top, width, height: options.height ?? 34 },
    {
      fill: options.fill ?? COLORS.mint,
      line: { style: "solid", fill: options.lineColor ?? "none", width: 0 },
      borderRadius: "rounded-full",
    },
  );
  textbox(
    slide,
    name,
    text,
    { left: left + 10, top: top + 1, width: width - 20, height: (options.height ?? 34) - 2 },
    {
      fontSize: options.fontSize ?? 15,
      bold: options.bold ?? true,
      color: options.color ?? COLORS.green,
      alignment: options.alignment ?? "center",
      verticalAlignment: "middle",
    },
  );
}

function addMetricCard(slide, name, x, y, width, value, label, options = {}) {
  rect(
    slide,
    `${name}-card`,
    { left: x, top: y, width, height: options.height ?? 128 },
    {
      fill: options.fill ?? COLORS.paper,
      lineColor: options.lineColor ?? COLORS.line,
      borderRadius: "rounded-xl",
      shadow: "shadow-sm",
    },
  );
  textbox(
    slide,
    `${name}-value`,
    value,
    { left: x + 18, top: y + 16, width: width - 36, height: 48 },
    {
      fontSize: options.valueSize ?? 34,
      bold: true,
      color: options.valueColor ?? COLORS.green,
      verticalAlignment: "middle",
    },
  );
  textbox(
    slide,
    `${name}-label`,
    label,
    { left: x + 18, top: y + 73, width: width - 36, height: 38 },
    { fontSize: 16, color: COLORS.muted },
  );
}

function addCard(slide, name, x, y, width, height, title, body, options = {}) {
  rect(
    slide,
    `${name}-card`,
    { left: x, top: y, width, height },
    {
      fill: options.fill ?? COLORS.paper,
      lineColor: options.lineColor ?? COLORS.line,
      borderRadius: "rounded-xl",
      shadow: options.shadow ?? "shadow-sm",
    },
  );
  if (options.number) {
    circle(
      slide,
      `${name}-number`,
      x + 18,
      y + 18,
      34,
      options.numberFill ?? COLORS.orange,
      options.number,
    );
  }
  textbox(
    slide,
    `${name}-title`,
    title,
    {
      left: x + (options.number ? 66 : 20),
      top: y + 18,
      width: width - (options.number ? 86 : 40),
      height: 34,
    },
    { fontSize: 22, bold: true, color: options.titleColor ?? COLORS.green, verticalAlignment: "middle" },
  );
  textbox(
    slide,
    `${name}-body`,
    body,
    { left: x + 20, top: y + 64, width: width - 40, height: height - 82 },
    { fontSize: options.bodySize ?? 16, color: options.bodyColor ?? COLORS.muted },
  );
}

function addScreenshot(slide, name, imageBytes, position, alt) {
  rect(
    slide,
    `${name}-frame`,
    position,
    {
      fill: COLORS.paper,
      lineColor: COLORS.green,
      lineWidth: 1,
      borderRadius: "rounded-xl",
      shadow: "shadow-md",
    },
  );
  slide.images.add({
    blob: imageBytes,
    contentType: "image/png",
    alt,
    fit: "contain",
    position: {
      left: position.left + 8,
      top: position.top + 8,
      width: position.width - 16,
      height: position.height - 16,
    },
    geometry: "roundRect",
    borderRadius: "rounded-lg",
  });
}

function setNotes(slide, body, sources = []) {
  const block = sources.length
    ? `\n\n[Sources]\n${sources.map((source) => `- ${source}`).join("\n")}\n[/Sources]`
    : "";
  slide.speakerNotes.textFrame.setText(`${body}${block}`);
  slide.speakerNotes.setVisible(true);
}

function makeDeck() {
  return Presentation.create({ slideSize: { width: 1280, height: 720 } });
}

async function main() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.mkdir(SUBMISSION_DIR, { recursive: true });

  const home = await readImageBlob(path.join(SUBMISSION_DIR, "assets", "labtrace-home.png"));
  const review = await readImageBlob(path.join(SUBMISSION_DIR, "assets", "labtrace-review.png"));
  const diagnosis = await readImageBlob(path.join(SUBMISSION_DIR, "assets", "labtrace-diagnosis.png"));

  const presentation = makeDeck();
  presentation.theme.colorScheme = {
    name: "LabTrace",
    themeColors: {
      accent1: COLORS.green,
      accent2: COLORS.orange,
      accent3: COLORS.mint2,
      accent4: COLORS.danger,
      accent5: COLORS.yellow,
      accent6: COLORS.muted,
      bg1: COLORS.cream,
      bg2: COLORS.paper,
      tx1: COLORS.ink,
      tx2: COLORS.muted,
      dk1: COLORS.forest,
      dk2: COLORS.green,
      lt1: COLORS.white,
      lt2: COLORS.mint,
      hlink: COLORS.orange,
      folHlink: COLORS.danger,
    },
  };

  // 01 — Sparse cover based on Codex Grid slide-01.
  {
    const slide = presentation.slides.add();
    slide.background.fill = COLORS.cream;
    rect(
      slide,
      "cover-accent",
      { left: 0, top: 0, width: 24, height: 720 },
      { geometry: "rect", fill: COLORS.orange, line: { style: "solid", fill: COLORS.orange, width: 0 } },
    );
    textbox(
      slide,
      "cover-kicker",
      "GOAI 2026 · 无界应用 / AI+教育",
      { left: 54, top: 42, width: 500, height: 40 },
      { fontSize: 20, bold: true, color: COLORS.orange },
    );
    textbox(
      slide,
      "cover-title",
      "格物智评\nLabTrace",
      { left: 54, top: 176, width: 730, height: 240 },
      { fontSize: 76, bold: true, color: COLORS.green, verticalAlignment: "bottom" },
    );
    textbox(
      slide,
      "cover-subtitle",
      "高校实验报告证据化批改 Agent",
      { left: 56, top: 440, width: 720, height: 48 },
      { fontSize: 30, bold: true, color: COLORS.ink },
    );
    textbox(
      slide,
      "cover-tagline",
      "让每一分回到证据，让每次批改进入教学闭环。",
      { left: 56, top: 510, width: 760, height: 44 },
      { fontSize: 23, color: COLORS.muted },
    );
    addPill(slide, "cover-team", "单人团队：独立变量", 56, 594, 230, {
      fill: COLORS.green,
      color: COLORS.white,
      fontSize: 16,
    });
    addPill(slide, "cover-status", "可运行 Demo · 合成数据", 304, 594, 246, {
      fill: COLORS.orangeSoft,
      color: COLORS.danger,
      fontSize: 16,
    });
    rect(
      slide,
      "cover-mark",
      { left: 984, top: 124, width: 170, height: 170 },
      { geometry: "ellipse", fill: COLORS.green, line: { style: "solid", fill: COLORS.green, width: 0 } },
    );
    textbox(
      slide,
      "cover-mark-text",
      "证\n据",
      { left: 1016, top: 151, width: 106, height: 116 },
      { fontSize: 46, bold: true, color: COLORS.cream, alignment: "center", verticalAlignment: "middle" },
    );
    setNotes(
      slide,
      "开场：这不是自动打分器，而是让教师可以复核证据、接管不确定项、再把结果沉淀为教学诊断的 Agent。",
      [
        "https://www.goaihz.com/tracks?track=apps",
        "https://oss.goaihz.com/prod/20260716/eed923c4-570c-4f5e-bb18-4f451fb97ced.pdf",
      ],
    );
  }

  // 02 — Half text, half visual based on Codex Grid slide-08.
  {
    const slide = baseSlide(presentation, "教师缺的不是第二个打分器", 2, "01 · 场景价值");
    textbox(
      slide,
      "pain-quote",
      "真正费时的是：\n找证据、判异常、写批注、做汇总。",
      { left: 42, top: 178, width: 530, height: 122 },
      { fontSize: 30, bold: true, color: COLORS.green },
    );
    addCard(slide, "pain-1", 42, 330, 252, 138, "多模态材料", "正文、表格、代码、截图与结果图需要交叉核对。", {
      fill: COLORS.paper,
      titleColor: COLORS.orange,
      bodySize: 15,
    });
    addCard(slide, "pain-2", 314, 330, 252, 138, "评分可解释", "只有总分无法定位依据，也无法支持申诉与复核。", {
      fill: COLORS.paper,
      titleColor: COLORS.orange,
      bodySize: 15,
    });
    addCard(slide, "pain-3", 42, 486, 524, 138, "批改没有进入下一次教学", "个体反馈散落在文档里，班级共性薄弱点仍靠教师凭印象总结。", {
      fill: COLORS.mint,
      lineColor: COLORS.mint2,
      bodySize: 16,
    });
    addScreenshot(
      slide,
      "pain-demo",
      home,
      { left: 638, top: 164, width: 600, height: 468 },
      "LabTrace 任务闭环首页",
    );
    setNotes(slide, "对应赛道重点：真实教学辅助场景、完整用户流程、非泛问答。右侧为本地运行 Demo 截图。");
  }

  // 03 — Six-step product loop.
  {
    const slide = baseSlide(presentation, "一条可演示、可验证、可接管的任务闭环", 3, "02 · 产品闭环");
    const cards = [
      ["1", "确认标准", "实验要求转为教师可编辑 rubric；总分先校验。"],
      ["2", "解析报告", "提取正文、表格与图片，保留原文定位。"],
      ["3", "寻找证据", "逐维度建立 evidence_id，而不是只写理由。"],
      ["4", "生成建议", "输出分项分数、置信度、反馈与风险标记。"],
      ["5", "教师复核", "低置信或冲突项强制进入人工调整与留痕。"],
      ["6", "交付诊断", "回写批注、发布成绩、聚合班级薄弱点。"],
    ];
    cards.forEach((item, index) => {
      const col = index % 3;
      const row = Math.floor(index / 3);
      addCard(
        slide,
        `loop-${index + 1}`,
        42 + col * 404,
        170 + row * 230,
        374,
        196,
        item[1],
        item[2],
        {
          number: item[0],
          fill: row === 0 ? COLORS.paper : COLORS.mint,
          lineColor: row === 0 ? COLORS.line : COLORS.mint2,
          bodySize: 17,
        },
      );
    });
    addPill(slide, "loop-boundary", "AI 给建议 · 教师定结果", 506, 618, 268, {
      fill: COLORS.green,
      color: COLORS.white,
      height: 38,
    });
    setNotes(
      slide,
      "演示时按 1—6 顺序快速走读。强调第 5 步不是补丁，而是教育评价边界的一部分。",
      ["goaihz/docs/product.md"],
    );
  }

  // 04 — Demo landing / direct proof.
  {
    const slide = baseSlide(presentation, "无密钥也能现场跑通，结果可复现", 4, "03 · DEMO / 任务启动");
    addScreenshot(
      slide,
      "demo-home",
      home,
      { left: 42, top: 156, width: 790, height: 490 },
      "LabTrace 演示首页与任务步骤",
    );
    addMetricCard(slide, "demo-doc", 866, 168, 336, "22 / 7 / 1", "解析：段落 / 表格 / 图片", {
      fill: COLORS.paper,
      valueSize: 31,
    });
    addMetricCard(slide, "demo-score", 866, 316, 336, "74 分", "Agent 初始评分建议", {
      fill: COLORS.mint,
      valueColor: COLORS.green,
    });
    addMetricCard(slide, "demo-proof", 866, 464, 336, "9 条", "可定位 evidence 引用", {
      fill: COLORS.orangeSoft,
      valueColor: COLORS.danger,
    });
    textbox(
      slide,
      "demo-disclaimer",
      "人工合成温度传感实验报告；规则型适配器保证现场稳定，接口可切换真实模型。",
      { left: 866, top: 600, width: 336, height: 44 },
      { fontSize: 14, color: COLORS.muted },
    );
    setNotes(
      slide,
      "点击“载入合成样例”并运行 Agent。当前演示数据完全人工构造，现场不依赖模型密钥。",
      [
        "goaihz/submission/assets/labtrace-home.png",
        "goaihz/data/synthetic/demo-student-001_实验报告.docx",
      ],
    );
  }

  // 05 — Evidence ledger and uncertainty.
  {
    const slide = baseSlide(presentation, "低置信度不是藏起来，而是交给教师", 5, "03 · DEMO / 证据与复核");
    addScreenshot(
      slide,
      "demo-review",
      review,
      { left: 42, top: 154, width: 856, height: 500 },
      "证据账本、低置信项与教师调整界面",
    );
    addPill(slide, "review-confidence", "分析维度置信度 68%", 936, 170, 262, {
      fill: COLORS.orangeSoft,
      color: COLORS.danger,
      height: 40,
      fontSize: 17,
    });
    addCard(slide, "review-evidence", 930, 234, 276, 124, "证据回指", "定位到报告段落与表格；缺失或冲突显式展示。", {
      titleColor: COLORS.green,
      bodySize: 15,
    });
    addCard(slide, "review-trigger", 930, 376, 276, 124, "复核触发", "分析与误差讨论不足，禁止自动发布成绩。", {
      fill: COLORS.orangeSoft,
      lineColor: COLORS.orange,
      titleColor: COLORS.danger,
      bodySize: 15,
    });
    addCard(slide, "review-audit", 930, 518, 276, 124, "留痕字段", "原建议、最终分、调整原因、时间与操作者。", {
      fill: COLORS.mint,
      lineColor: COLORS.mint2,
      bodySize: 15,
    });
    setNotes(
      slide,
      "演示时点开一条证据，再展示 68% 低置信提醒。系统不会在此状态自动发布。",
      ["goaihz/submission/assets/labtrace-review.png"],
    );
  }

  // 06 — Human in the loop to diagnosis.
  {
    const slide = baseSlide(presentation, "一次人工判断，同时服务个体反馈与班级讲评", 6, "03 · DEMO / 教师终审");
    addScreenshot(
      slide,
      "demo-diagnosis",
      diagnosis,
      { left: 42, top: 154, width: 770, height: 500 },
      "教师确认后的班级学情诊断",
    );
    textbox(
      slide,
      "review-transition",
      "74",
      { left: 866, top: 176, width: 120, height: 80 },
      { fontSize: 60, bold: true, color: COLORS.muted, alignment: "center", verticalAlignment: "middle" },
    );
    textbox(
      slide,
      "review-arrow",
      "→",
      { left: 982, top: 184, width: 70, height: 70 },
      { fontSize: 46, bold: true, color: COLORS.orange, alignment: "center", verticalAlignment: "middle" },
    );
    textbox(
      slide,
      "review-final",
      "76",
      { left: 1050, top: 176, width: 120, height: 80 },
      { fontSize: 60, bold: true, color: COLORS.green, alignment: "center", verticalAlignment: "middle" },
    );
    textbox(
      slide,
      "review-caption",
      "教师将“分析”维度 10 → 12，填写理由后确认发布。",
      { left: 862, top: 270, width: 330, height: 72 },
      { fontSize: 18, bold: true, color: COLORS.ink, alignment: "center" },
    );
    addMetricCard(slide, "class-count", 852, 378, 164, "4 份", "已复核样本", {
      height: 118,
      valueSize: 30,
    });
    addMetricCard(slide, "class-average", 1034, 378, 164, "75 分", "班级均分", {
      height: 118,
      valueSize: 30,
    });
    addMetricCard(slide, "class-weak", 852, 518, 346, "55%", "最弱维度达成率：分析与误差讨论", {
      height: 124,
      valueSize: 34,
      fill: COLORS.orangeSoft,
      valueColor: COLORS.danger,
    });
    setNotes(
      slide,
      "教师调整的不是一个孤立数字：它被保存为审计事件，并进入班级已复核数据的聚合。",
      ["goaihz/submission/assets/labtrace-diagnosis.png"],
    );
  }

  // 07 — Agent architecture.
  {
    const slide = baseSlide(presentation, "显式状态机 + 工具链，形成可审计 Agent", 7, "04 · 技术路线");
    const nodes = [
      ["Rubric", "标准确认"],
      ["Parse", "图文解析"],
      ["Evidence", "证据抽取"],
      ["Grade", "结构评分"],
      ["Verify", "规则校验"],
      ["Review", "教师复核"],
      ["Deliver", "批注诊断"],
    ];
    nodes.forEach((node, index) => {
      const x = 42 + index * 171;
      rect(
        slide,
        `arch-node-${index}`,
        { left: x, top: 190, width: 140, height: 102 },
        {
          fill: index === 5 ? COLORS.orangeSoft : index === 6 ? COLORS.green : COLORS.paper,
          lineColor: index === 5 ? COLORS.orange : COLORS.green,
          borderRadius: "rounded-xl",
        },
      );
      textbox(
        slide,
        `arch-code-${index}`,
        node[0],
        { left: x + 12, top: 207, width: 116, height: 28 },
        {
          fontSize: 15,
          bold: true,
          color: index === 6 ? COLORS.white : COLORS.orange,
          alignment: "center",
        },
      );
      textbox(
        slide,
        `arch-label-${index}`,
        node[1],
        { left: x + 12, top: 245, width: 116, height: 30 },
        {
          fontSize: 18,
          bold: true,
          color: index === 6 ? COLORS.white : COLORS.green,
          alignment: "center",
        },
      );
      if (index < nodes.length - 1) {
        textbox(
          slide,
          `arch-arrow-${index}`,
          "→",
          { left: x + 140, top: 216, width: 31, height: 44 },
          { fontSize: 28, bold: true, color: COLORS.muted, alignment: "center", verticalAlignment: "middle" },
        );
      }
    });
    addCard(slide, "arch-tools", 42, 350, 350, 220, "工具层", "DOCX/PDF 解析\n表格与图片抽取\n批注回写与文件导出", {
      fill: COLORS.mint,
      lineColor: COLORS.mint2,
      bodySize: 19,
    });
    addCard(slide, "arch-contract", 416, 350, 408, 220, "契约与校验层", "GradeTrace 证据契约\nevidence_id 与来源定位\n分项合计、置信度、复核状态", {
      fill: COLORS.paper,
      lineColor: COLORS.green,
      bodySize: 19,
    });
    addCard(slide, "arch-adapter", 848, 350, 390, 220, "双适配器运行", "无密钥规则型 Demo：现场稳定\nLLM / Vision 适配器：真实语义评分\n同一 rubric、工具协议与输出契约", {
      fill: COLORS.orangeSoft,
      lineColor: COLORS.orange,
      bodySize: 18,
    });
    addPill(slide, "arch-record", "每个状态记录：输入摘要 · 配置版本 · 工具结果 · 异常 · 审计事件", 222, 604, 836, {
      fill: COLORS.green,
      color: COLORS.white,
      height: 38,
      fontSize: 16,
    });
    setNotes(
      slide,
      "Agent 的自主性体现在：依据状态选择工具、构建证据、判断是否需要人类接管，并完成交付，而不是一条长 Prompt。",
      ["goaihz/docs/architecture.md"],
    );
  }

  // 08 — Four-point grid based on Codex Grid slide-13.
  {
    const slide = baseSlide(presentation, "技术深度落在四个可验证部件", 8, "04 · 工程实现");
    addCard(slide, "tech-1", 42, 166, 568, 206, "01 · 多模态结构解析", "读取段落、表格与嵌入图片；保留原文顺序和定位，失败时显式降级。", {
      fill: COLORS.paper,
      titleColor: COLORS.orange,
      bodySize: 18,
    });
    addCard(slide, "tech-2", 628, 166, 610, 206, "02 · GradeTrace 证据契约", "每个维度包含得分、依据、evidence_id、置信度与复核原因；总分由程序校验。", {
      fill: COLORS.mint,
      lineColor: COLORS.mint2,
      titleColor: COLORS.green,
      bodySize: 18,
    });
    addCard(slide, "tech-3", 42, 394, 568, 206, "03 · Human-in-the-loop", "低置信或证据冲突时禁止自动发布；教师调整保留前后值与原因。", {
      fill: COLORS.orangeSoft,
      lineColor: COLORS.orange,
      titleColor: COLORS.danger,
      bodySize: 18,
    });
    addCard(slide, "tech-4", 628, 394, 610, 206, "04 · 可替换模型与可复现演示", "显式工具协议隔离模型供应商；无密钥模式与真实模型模式共享 API、rubric 和测试。", {
      fill: COLORS.paper,
      titleColor: COLORS.orange,
      bodySize: 18,
    });
    addPill(slide, "tech-stack", "Vue 3 · TypeScript · FastAPI · python-docx · PyMuPDF · Docker Compose", 218, 620, 844, {
      fill: COLORS.green,
      color: COLORS.white,
      height: 36,
      fontSize: 15,
    });
    setNotes(
      slide,
      "四个部件都能在代码、接口响应或导出文件中被独立检查。现阶段不宣称真实教学准确率。",
      ["goaihz/docs/architecture.md"],
    );
  }

  // 09 — Data table based on Codex Grid slide-14.
  {
    const slide = baseSlide(presentation, "当前验证：不仅能看，还能重复跑", 9, "05 · 验证与可复现");
    textbox(
      slide,
      "verify-intro",
      "以下均为当前代码和合成样例的实测结果；教学准确率仍需授权教师金标集验证。",
      { left: 42, top: 144, width: 1120, height: 36 },
      { fontSize: 18, color: COLORS.muted },
    );
    const values = [
      ["验证层", "检查项", "当前结果", "证据"],
      ["单元 / API", "参赛模块测试", "9 / 9 通过", "pytest"],
      ["回归", "根项目测试", "49 通过 / 21 跳过", "pytest"],
      ["Agent 闭环", "评分 → 调整 → 发布 → 诊断", "通过", "FastAPI 测试"],
      ["文档交付", "原生 Word 批注与总分", "5 条批注 / 74 分", "DOCX 结构检查"],
      ["浏览器", "公共入口与六步交互", "通过", "无 console 错误"],
      ["隐私", "合成数据敏感模式扫描", "通过", "验证脚本"],
    ];
    const table = slide.tables.add({
      rows: values.length,
      columns: 4,
      left: 42,
      top: 202,
      width: 1196,
      height: 392,
      columnWidths: [180, 390, 230, 396],
      values,
    });
    table.borders.assign({ style: "solid", fill: COLORS.line, width: 1 });
    table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: 4 }).assign({
      fill: COLORS.green,
      textStyle: { typeface: FONT, fontSize: 17, bold: true, color: COLORS.white },
      margins: { top: 10, right: 10, bottom: 10, left: 10 },
      verticalAlignment: "middle",
    });
    table.cells.block({ row: 1, column: 0, rowCount: values.length - 1, columnCount: 4 }).assign({
      textStyle: { typeface: FONT, fontSize: 15, color: COLORS.ink },
      margins: { top: 8, right: 10, bottom: 8, left: 10 },
      verticalAlignment: "middle",
    });
    for (let column = 0; column < 4; column += 1) {
      table.getCell(0, column).text.style = {
        typeface: FONT,
        fontSize: 17,
        bold: true,
        color: COLORS.white,
      };
    }
    for (let row = 1; row < values.length; row += 1) {
      if (row % 2 === 0) {
        table.cells.block({ row, column: 0, rowCount: 1, columnCount: 4 }).fill = COLORS.mint;
      }
    }
    addPill(slide, "verify-boundary", "未验证项：教师一致性、真实样本 MAE、节省时间比例", 386, 618, 508, {
      fill: COLORS.orangeSoft,
      color: COLORS.danger,
      height: 36,
      fontSize: 15,
    });
    setNotes(
      slide,
      "明确边界：当前结果证明工程可运行、证据链可生成、复核可留痕；不等于已经证明教学成效。",
      [
        "goaihz/tests/test_competition_profile.py",
        "goaihz/docs/evaluation.md",
      ],
    );
  }

  // 10 — Safety, compliance and openness.
  {
    const slide = baseSlide(presentation, "把教育边界写进产品，而不是写在免责声明里", 10, "06 · 安全、合规与开放");
    addCard(slide, "safe-1", 42, 166, 276, 210, "数据最小化", "公开 Demo 仅用人工合成数据；真实部署默认本地或指定私有环境。", {
      fill: COLORS.mint,
      lineColor: COLORS.mint2,
      titleColor: COLORS.green,
      bodySize: 17,
    });
    addCard(slide, "safe-2", 344, 166, 276, 210, "教师最终决定", "AI 只给建议；低置信、证据冲突和解析失败必须人工接管。", {
      fill: COLORS.orangeSoft,
      lineColor: COLORS.orange,
      titleColor: COLORS.danger,
      bodySize: 17,
    });
    addCard(slide, "safe-3", 646, 166, 276, 210, "可审计与可删除", "保存配置版本、原建议、调整原因与异常；原件和中间产物可按策略删除。", {
      fill: COLORS.paper,
      bodySize: 17,
    });
    addCard(slide, "safe-4", 948, 166, 290, 210, "开放边界清晰", "优先开放 rubric、证据契约、模拟数据、诊断模块、评测与复现文档。", {
      fill: COLORS.paper,
      titleColor: COLORS.orange,
      bodySize: 17,
    });
    rect(
      slide,
      "safe-boundary-card",
      { left: 42, top: 412, width: 1196, height: 180 },
      {
        fill: COLORS.green,
        line: { style: "solid", fill: COLORS.green, width: 0 },
        borderRadius: "rounded-xl",
      },
    );
    textbox(
      slide,
      "safe-boundary-title",
      "公开提交边界",
      { left: 72, top: 438, width: 230, height: 34 },
      { fontSize: 24, bold: true, color: COLORS.orangeSoft },
    );
    textbox(
      slide,
      "safe-boundary-body",
      "不上传真实姓名、学号、联系方式、成绩文件、教师签名、生产日志或密钥。\n商业 API 仅在披露调用环节、发送字段、费用、存储策略和本地替代路线后使用。",
      { left: 72, top: 488, width: 1110, height: 76 },
      { fontSize: 18, color: COLORS.white },
    );
    addPill(slide, "safe-license", "根仓库暂无明确 LICENSE：公开前先完成权属与第三方许可审查", 274, 618, 732, {
      fill: COLORS.orangeSoft,
      color: COLORS.danger,
      height: 36,
      fontSize: 15,
    });
    setNotes(
      slide,
      "风险控制不是泛泛承诺：Demo 数据、路由行为、复核门槛、审计字段和开源清单都有对应实现或文档。",
      [
        "goaihz/docs/compliance.md",
        "goaihz/docs/open_source_boundary.md",
      ],
    );
  }

  // 11 — Gantt-style roadmap based on Codex Grid slide-24.
  {
    const slide = baseSlide(presentation, "按更早截止线推进：先稳交付，再做真实评测", 11, "07 · 里程碑");
    const headers = ["7/29", "8/5", "8/16", "9/3", "9/22–23"];
    const x0 = 42;
    const y0 = 170;
    const colW = 239.2;
    headers.forEach((header, index) => {
      textbox(
        slide,
        `road-header-${index}`,
        header,
        { left: x0 + index * colW + 10, top: y0, width: colW - 20, height: 36 },
        { fontSize: 17, bold: true, color: index === 2 || index === 3 ? COLORS.orange : COLORS.green },
      );
      line(
        slide,
        `road-vline-${index}`,
        { left: x0 + index * colW, top: y0 + 44, width: 0, height: 370 },
        COLORS.line,
        1,
      );
    });
    line(slide, "road-vline-end", { left: 1238, top: y0 + 44, width: 0, height: 370 }, COLORS.line, 1);
    const bars = [
      [0, 2, 228, "可运行 Demo、合成样例与初赛材料", COLORS.green, COLORS.white],
      [1, 2, 296, "录制 2–3 分钟视频、提交与备份", COLORS.orange, COLORS.white],
      [2, 2, 364, "接入真实模型、教师金标集与批量评测", COLORS.mint2, COLORS.green],
      [2, 3, 432, "权限 / 删除策略、稳定性与失败注入", COLORS.paper, COLORS.ink],
      [3, 2, 500, "离线包、依赖锁定、路演与答辩预案", COLORS.orangeSoft, COLORS.danger],
    ];
    bars.forEach((bar, index) => {
      const [start, span, top, label, fill, color] = bar;
      rect(
        slide,
        `road-bar-${index}`,
        { left: x0 + start * colW + 12, top, width: span * colW - 24, height: 48 },
        {
          fill,
          line: { style: "solid", fill: fill === COLORS.paper ? COLORS.line : fill, width: 1 },
          borderRadius: "rounded-lg",
        },
      );
      textbox(
        slide,
        `road-label-${index}`,
        label,
        { left: x0 + start * colW + 28, top: top + 7, width: span * colW - 56, height: 34 },
        { fontSize: 16, bold: true, color, verticalAlignment: "middle" },
      );
    });
    addPill(slide, "road-risk", "官网与手册复赛日期不一致：项目内部按 9 月 3 日冻结候选版", 330, 618, 620, {
      fill: COLORS.orangeSoft,
      color: COLORS.danger,
      height: 36,
      fontSize: 15,
    });
    setNotes(
      slide,
      "官网赛道页显示复赛到 9 月 23 日，但 2026-07-16 手册与公开配置指向 9 月 3 日；按更早日期倒排并向组委会确认。",
      [
        "https://www.goaihz.com/tracks?track=apps",
        "https://oss.goaihz.com/prod/20260716/eed923c4-570c-4f5e-bb18-4f451fb97ced.pdf",
        "goaihz/docs/competition_notes.md",
      ],
    );
  }

  // 12 — Closing based on Codex Grid slide-26.
  {
    const slide = presentation.slides.add();
    slide.background.fill = COLORS.green;
    rect(
      slide,
      "close-accent",
      { left: 0, top: 0, width: 24, height: 720 },
      { geometry: "rect", fill: COLORS.orange, line: { style: "solid", fill: COLORS.orange, width: 0 } },
    );
    textbox(
      slide,
      "close-kicker",
      "独立变量 · 格物智评 LABTRACE",
      { left: 54, top: 42, width: 500, height: 36 },
      { fontSize: 20, bold: true, color: COLORS.orangeSoft },
    );
    textbox(
      slide,
      "close-title",
      "让每一分\n回到证据",
      { left: 54, top: 172, width: 760, height: 256 },
      { fontSize: 76, bold: true, color: COLORS.white, verticalAlignment: "bottom" },
    );
    textbox(
      slide,
      "close-detail",
      "可接管的不确定性\n可复核的教师终审\n可迁移的课程模板",
      { left: 58, top: 506, width: 430, height: 114 },
      { fontSize: 24, color: COLORS.mint },
    );
    rect(
      slide,
      "close-right",
      { left: 814, top: 126, width: 370, height: 452 },
      {
        fill: COLORS.paper,
        line: { style: "solid", fill: COLORS.paper, width: 0 },
        borderRadius: "rounded-xl",
      },
    );
    textbox(
      slide,
      "close-right-title",
      "一套高校教师可终审、\n开发者可复用的批改 Agent 模板",
      { left: 850, top: 180, width: 300, height: 120 },
      { fontSize: 29, bold: true, color: COLORS.green },
    );
    textbox(
      slide,
      "close-right-body",
      "✓ 真实任务闭环\n✓ 可运行 Demo\n✓ 合成数据与测试\n✓ PPT / PDF / 说明材料\n✓ 可复现部署路径",
      { left: 850, top: 344, width: 300, height: 170 },
      { fontSize: 21, color: COLORS.ink },
    );
    setNotes(
      slide,
      "收束：LabTrace 不替教师下结论，它把机械核对交给 Agent，把不确定性还给教师，把批改结果沉淀为教学反馈。",
      ["goaihz/docs/product.md"],
    );
  }

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await presentation.export({ slide, format: "png", scale: 1 });
    await writeBlob(path.join(OUT_DIR, `${stem}.png`), png);
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(OUT_DIR, `${stem}.layout.json`), await layout.text());
  }

  const montageColumns = 3;
  const montageRows = 4;
  const thumbWidth = 384;
  const thumbHeight = 216;
  const montagePadding = 24;
  const montageGap = 18;
  const montageWidth =
    montagePadding * 2 + montageColumns * thumbWidth + (montageColumns - 1) * montageGap;
  const montageHeight =
    montagePadding * 2 + montageRows * thumbHeight + (montageRows - 1) * montageGap;
  const composites = [];
  for (let index = 0; index < presentation.slides.items.length; index += 1) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    composites.push({
      input: await sharp(path.join(OUT_DIR, `${stem}.png`))
        .resize(thumbWidth, thumbHeight, { fit: "fill" })
        .png()
        .toBuffer(),
      left: montagePadding + (index % montageColumns) * (thumbWidth + montageGap),
      top:
        montagePadding +
        Math.floor(index / montageColumns) * (thumbHeight + montageGap),
    });
  }
  await sharp({
    create: {
      width: montageWidth,
      height: montageHeight,
      channels: 4,
      background: COLORS.paper,
    },
  })
    .composite(composites)
    .png()
    .toFile(path.join(OUT_DIR, "labtrace-deck-montage.png"));

  const pptx = await PresentationFile.exportPptx(presentation);
  const deckPath = path.join(SUBMISSION_DIR, "格物智评_LabTrace_GOAI初赛方案.pptx");
  await pptx.save(deckPath);
  const inspectPath = `${deckPath}.inspect.ndjson`;
  try {
    await fs.rename(inspectPath, path.join(OUT_DIR, path.basename(inspectPath)));
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
