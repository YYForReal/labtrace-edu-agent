<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  deleteLabTraceTask,
  getLabTraceBootstrap,
  gradeLabTraceDemo,
  labTraceDownloadUrl,
  labTracePublicUrl,
  reviewLabTraceDemo,
  type LabTraceBootstrap,
  type LabTraceTask,
} from '@/api'

const bootstrap = ref<LabTraceBootstrap | null>(null)
const selectedFile = ref<File | null>(null)
const rubricFile = ref<File | null>(null)
const allowExternalImages = ref(false)
const task = ref<LabTraceTask | null>(null)
const loading = ref(false)
const sampleLoading = ref(false)
const reviewing = ref(false)
const deleting = ref(false)
const selectedSampleId = ref('allergen')
const reviewSuggestionScore = ref(0)
const reviewNote = ref('已核对证据定位与评分标准，并完成教师终审。')
const fileInput = ref<HTMLInputElement>()
const rubricInput = ref<HTMLInputElement>()

const totalScore = computed(() => {
  if (!task.value) return 0
  return task.value.trace.criteria.reduce((sum, item) => sum + Number(item.score || 0), 0)
})

const evidenceMap = computed(() => {
  const result: Record<string, LabTraceTask['trace']['evidence'][number]> = {}
  for (const item of task.value?.trace.evidence || []) result[item.evidence_id] = item
  return result
})

const profileFacts = computed(() => {
  const profile = task.value?.document_profile || {}
  return [
    ['正文段落', profile.paragraph_count ?? 0],
    ['数据表格', profile.table_count ?? 0],
    ['结果图像', profile.image_count ?? 0],
  ]
})

const completed = computed(() => task.value?.status === 'completed')
const reviewTarget = computed(() => {
  if (!task.value) return undefined
  return [...task.value.trace.criteria].sort(
    (a, b) => a.confidence - b.confidence || a.score / a.max_score - b.score / b.max_score,
  )[0]
})
const teacherAdjustment = computed(() => {
  const criterion = reviewTarget.value
  const from = reviewSuggestionScore.value || Number(criterion?.score || 0)
  return {
    from,
    to: Math.min(from + 2, Number(criterion?.max_score || from + 2)),
  }
})

onMounted(async () => {
  try {
    bootstrap.value = (await getLabTraceBootstrap()).data
  } catch {
    ElMessage.error('演示服务尚未启动，请按运行说明启动后刷新页面。')
  }
})

function chooseFile(event: Event) {
  const files = (event.target as HTMLInputElement).files
  selectedFile.value = files?.[0] || null
  task.value = null
}

function chooseRubric(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  if (file && (!file.name.toLowerCase().endsWith('.json') || file.size > 256 * 1024)) {
    ElMessage.error('评分标准必须是 256 KB 以内的 JSON 文件')
    rubricFile.value = null
    return
  }
  rubricFile.value = file
  task.value = null
}

async function loadSample(sampleId = selectedSampleId.value) {
  if (!bootstrap.value) return
  const sample = bootstrap.value.samples.find(item => item.id === sampleId)
  if (!sample) return
  selectedSampleId.value = sampleId
  sampleLoading.value = true
  try {
    const response = await fetch(labTracePublicUrl(sample.input_url))
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const blob = await response.blob()
    selectedFile.value = new File([blob], sample.filename, {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    task.value = null
    ElMessage.success(`已载入：${sample.name}`)
  } catch {
    ElMessage.error('样例报告尚未生成，请先运行数据构建脚本。')
  } finally {
    sampleLoading.value = false
  }
}

async function runAgent() {
  if (!selectedFile.value) {
    ElMessage.warning('请先载入样例或选择一份 DOCX / PDF 报告')
    return
  }
  loading.value = true
  task.value = null
  try {
    task.value = (
      await gradeLabTraceDemo(
        selectedFile.value,
        rubricFile.value,
        allowExternalImages.value,
      )
    ).data
    reviewSuggestionScore.value = Number(reviewTarget.value?.score || 0)
    reviewNote.value = `已核对证据定位与评分标准；将“${reviewTarget.value?.criterion_name || '待复核维度'}”从 ${teacherAdjustment.value.from} 分调整为 ${teacherAdjustment.value.to} 分后确认发布。`
    ElMessage.success(
      task.value.mode === 'model_agent'
        ? '真实模型建议与证据链已生成，现已转交教师终审'
        : '证据链已生成；本次使用可复现规则或显式降级路径',
    )
    requestAnimationFrame(() => document.querySelector('#trace-result')?.scrollIntoView({ behavior: 'smooth' }))
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '报告处理失败')
  } finally {
    loading.value = false
  }
}

function applyTeacherAdjustment() {
  const target = reviewTarget.value
  if (target) {
    target.score = teacherAdjustment.value.to
    ElMessage.info(`已应用教师调整：${target.criterion_name} ${teacherAdjustment.value.from} → ${teacherAdjustment.value.to} 分`)
  }
}

async function submitReview() {
  if (!task.value) return
  reviewing.value = true
  try {
    task.value = (await reviewLabTraceDemo(
      task.value.task_id,
      task.value.trace.criteria.map(item => ({
        criterion_id: item.criterion_id,
        score: Number(item.score),
        reason: item.reason,
      })),
      reviewNote.value,
    )).data
    ElMessage.success('教师终审完成，成绩与学情诊断已发布')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '终审提交失败')
  } finally {
    reviewing.value = false
  }
}

async function deleteTaskData() {
  if (!task.value) return
  deleting.value = true
  try {
    await deleteLabTraceTask(task.value.task_id)
    task.value = null
    selectedFile.value = null
    rubricFile.value = null
    ElMessage.success('本次上传、证据链和交付物已删除')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '删除失败，请稍后重试')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="labtrace-page">
    <header class="topbar">
      <a class="brand" href="#top" aria-label="格物智评首页">
        <span class="brand-mark">格</span>
        <span>
          <strong>格物智评 <em>LabTrace</em></strong>
          <small>高校实验报告批改 Agent</small>
        </span>
      </a>
      <div class="top-meta">
        <span class="live-dot"></span>
        <span>{{ bootstrap?.mode.external_processing ? '真实模型在线' : '可离线复现' }}</span>
        <span class="top-rule"></span>
        <span>GOAI 2026 · AI+教育</span>
      </div>
    </header>

    <main id="top">
      <section class="hero">
        <div class="hero-copy">
          <p class="eyebrow">NATIVE WORD GRADING AGENT</p>
          <h1>上传一份图文 Word，<br><span>交还一份已批注、可编辑的 Word。</span></h1>
          <p class="hero-lead">
            不把批改结果困在聊天框里。LabTrace 保留报告正文、表格和图片，
            将证据化批注、分项成绩与教师评语写回原生 Word，再交由教师终审。
          </p>
          <div class="hero-actions">
            <button class="primary-btn" :disabled="sampleLoading" @click="loadSample()">
              {{ sampleLoading ? '载入中…' : '载入匿名样例' }}
            </button>
            <a class="text-link" href="#workflow">查看任务闭环 <span>↘</span></a>
          </div>
        </div>
        <aside class="hero-card">
          <div class="card-label">核心交付</div>
          <div class="mode-title">
            <span class="mode-icon">W</span>
            <div>
              <strong>图文 Word → 可编辑批注 Word</strong>
              <small>
                {{ bootstrap?.mode.external_processing
                  ? `${bootstrap.mode.label} · 图片逐任务授权`
                  : '真实解析 · 显式规则 · 原生交付' }}
              </small>
            </div>
          </div>
          <p>{{ bootstrap?.product.promise || '原文不改写，批注有定位，教师评语可回填。' }}</p>
          <div class="mode-grid">
            <div><b>DOCX</b><span>原生结构</span></div>
            <div><b>图+文</b><span>联合证据</span></div>
            <div><b>批注</b><span>教师交付</span></div>
          </div>
        </aside>
      </section>

      <section id="workflow" class="workflow">
        <div class="section-heading">
          <p class="eyebrow">TASK LOOP</p>
          <h2>真正闭环，是把判断写回教师正在使用的文档</h2>
          <p>从课程标准、图文证据和模型建议，一直走到原生批注、教师评语与可编辑 Word 交付。</p>
        </div>
        <div class="step-rail">
          <div v-for="(step, index) in bootstrap?.agent_steps" :key="step.id" class="step-item">
            <span class="step-number">0{{ index + 1 }}</span>
            <strong>{{ step.label }}</strong>
            <small>{{ step.detail }}</small>
          </div>
        </div>
      </section>

      <section class="workbench">
        <div class="workbench-head">
          <div>
            <p class="eyebrow">LIVE DEMO</p>
            <h2>提交一份图文 Word，完整走一遍原生批改交付</h2>
          </div>
          <span class="privacy-pill">
            {{ bootstrap?.mode.external_processing
              ? '正文先脱敏；图片只有教师单次授权后才发送'
              : '公开样例均为匿名合成图文 Word' }}
          </span>
        </div>

        <div v-if="bootstrap" class="fixture-strip">
          <div>
            <span class="rubric-label">PUBLIC TEST KIT</span>
            <strong>1 份脱敏实验任务书 + 2 份全合成学生报告</strong>
            <small>{{ bootstrap.assignment_template.description }}</small>
          </div>
          <a
            class="template-download"
            :href="labTracePublicUrl(bootstrap.assignment_template.input_url)"
            :download="bootstrap.assignment_template.filename"
          >
            下载实验任务书 Word ↗
          </a>
        </div>

        <div class="sample-grid" aria-label="匿名演示案例">
          <button
            v-for="sample in bootstrap?.samples"
            :key="sample.id"
            class="sample-option"
            :class="{ active: selectedSampleId === sample.id }"
            type="button"
            @click="loadSample(sample.id)"
          >
            <span>{{ sample.domain }}</span>
            <strong>{{ sample.name }}</strong>
            <small>{{ sample.provenance }}</small>
          </button>
        </div>

        <div class="upload-panel" :class="{ ready: selectedFile }">
          <input ref="fileInput" hidden type="file" accept=".docx,.pdf" @change="chooseFile">
          <button class="file-icon" @click="fileInput?.click()">WORD</button>
          <div class="file-copy">
            <strong>{{ selectedFile?.name || '尚未选择实验报告' }}</strong>
            <span>{{ selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB · 将保留图文结构` : 'DOCX 优先：支持原生批注与教师评语；PDF 返回证据链' }}</span>
          </div>
          <button class="secondary-btn" @click="fileInput?.click()">选择文件</button>
          <button class="primary-btn run-btn" :disabled="loading || !selectedFile" @click="runAgent">
            {{ loading ? 'Agent 执行中…' : '运行批改 Agent' }}
          </button>
        </div>

        <div class="rubric-panel">
          <input ref="rubricInput" hidden type="file" accept=".json,application/json" @change="chooseRubric">
          <div>
            <span class="rubric-label">COURSE RUBRIC</span>
            <strong>{{ rubricFile?.name || bootstrap?.rubric.experiment_name || '内置通用评分标准' }}</strong>
            <small>
              {{ rubricFile
                ? '将按教师上传的课程维度、满分和评分规则执行'
                : '默认使用 6 维高校通用实验报告标准，也可接入真实课程 JSON' }}
            </small>
          </div>
          <button class="secondary-btn" type="button" @click="rubricInput?.click()">选择课程 Rubric</button>
          <a
            v-if="bootstrap"
            class="rubric-template"
            :href="labTracePublicUrl(bootstrap.rubric_template_url)"
          >
            下载 JSON 模板 ↗
          </a>
        </div>

        <div v-if="bootstrap?.mode.external_processing" class="data-notice">
          <strong>真实数据边界</strong>
          <div>
            <span>{{ bootstrap.data_policy.identity_redaction }}；{{ bootstrap.data_policy.model_payload }}。</span>
            <span>{{ bootstrap.data_policy.teacher_responsibility }}。</span>
            <label class="image-consent">
              <input v-model="allowExternalImages" type="checkbox">
              <span>我已确认图片无未授权身份信息，同意分析至多 4 张图片，并将图片判断定位回 Word 原段落</span>
            </label>
          </div>
        </div>

        <div v-if="loading" class="running-panel">
          <div class="scan-orbit"><span></span></div>
          <div>
            <strong>正在建立证据链</strong>
            <p>解析 Word 图文结构 → 身份脱敏 → 图文联合判断 → 契约校验 → 生成原生批注</p>
          </div>
          <div class="progress-line"><span></span></div>
        </div>
      </section>

      <section v-if="task" id="trace-result" class="result-section">
        <div class="result-header">
          <div>
            <p class="eyebrow">AUDITABLE RESULT · {{ task.task_id }}</p>
            <h2>{{ completed ? '最终得分' : '建议得分' }} <span>{{ totalScore }}</span><small>/ {{ task.rubric.total_score }}</small></h2>
            <p>{{ completed ? '教师已确认；原始建议与调整记录完整保留。' : '发现低置信度判断，当前结果不会自动发布。' }}</p>
            <div class="run-badges">
              <span :class="{ fallback: task.agent_run.fallback }">
                {{ task.agent_run.fallback ? '显式降级' : task.agent_run.provider }}
                · {{ task.agent_run.model }}
              </span>
              <span>{{ task.rubric.source === 'teacher_upload' ? '教师 Rubric' : '内置 Rubric' }} · {{ task.rubric.experiment_name }}</span>
              <span v-if="task.agent_run.latency_ms">{{ (task.agent_run.latency_ms / 1000).toFixed(1) }} s</span>
              <span v-if="task.agent_run.tokens">{{ task.agent_run.tokens.input + task.agent_run.tokens.output }} tokens</span>
              <span>脱敏 {{ task.privacy.detected_sensitive_items }} 项</span>
              <span v-if="task.word_workflow.images_detected">
                图片 {{ task.word_workflow.images_detected }} 张 · 已分析 {{ task.word_workflow.images_analyzed }} 张
              </span>
            </div>
          </div>
          <div class="profile">
            <div v-for="fact in profileFacts" :key="String(fact[0])">
              <b>{{ fact[1] }}</b><span>{{ fact[0] }}</span>
            </div>
          </div>
        </div>

        <div v-if="task.word_workflow.input_is_word" class="word-delivery-banner">
          <div>
            <span>WORD-NATIVE DELIVERY</span>
            <strong>{{ completed ? '教师终审结果已写回 Word' : '可编辑批注 Word 已生成，等待教师终审' }}</strong>
          </div>
          <div class="delivery-facts">
            <span><b>{{ task.word_workflow.images_detected }}</b> 内嵌图片</span>
            <span><b>{{ task.word_workflow.image_comments }}</b> 图片定位批注</span>
            <span><b>{{ task.word_workflow.native_comments }}</b> 原生批注</span>
            <span><b>{{ task.word_workflow.teacher_feedback_written ? '已回填' : '待终审' }}</b> 教师评语</span>
          </div>
        </div>

        <div class="result-grid">
          <div class="criteria-panel">
            <div class="panel-title">
              <h3>逐项评分与证据账本</h3>
              <span>{{ task.trace.evidence.length }} 条可定位证据</span>
            </div>
            <article
              v-for="criterion in task.trace.criteria"
              :key="criterion.criterion_id"
              class="criterion-card"
              :class="{ uncertain: criterion.confidence < 0.75 }"
            >
              <div class="criterion-score">
                <span>{{ criterion.criterion_name }}</span>
                <div>
                  <input v-model.number="criterion.score" :max="criterion.max_score" min="0" step="0.5" type="number">
                  <small>/ {{ criterion.max_score }}</small>
                </div>
              </div>
              <p>{{ criterion.reason }}</p>
              <div class="criterion-meta">
                <span :class="{ warning: criterion.confidence < 0.75 }">
                  置信度 {{ Math.round(criterion.confidence * 100) }}%
                </span>
                <span v-if="criterion.confidence < 0.75" class="review-flag">需教师确认</span>
              </div>
              <div class="evidence-list">
                <div v-for="id in criterion.evidence_ids" :key="id" class="evidence-row">
                  <span class="locator">{{ evidenceMap[id]?.locator }}</span>
                  <div>
                    <q>{{ evidenceMap[id]?.excerpt }}</q>
                    <small
                      v-if="evidenceMap[id]?.kind === 'image_context'"
                      :class="{ observed: evidenceMap[id]?.verification === 'model_observed' }"
                    >
                      {{ evidenceMap[id]?.verification === 'model_observed'
                        ? '模型已查看授权图片 · 将定位回 Word'
                        : '仅使用图片邻近文本 · 未查看图片' }}
                    </small>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <aside class="review-panel">
            <div class="panel-kicker">HUMAN-IN-THE-LOOP</div>
            <h3>{{ completed ? '教师终审已完成' : '请教师确认低置信度判断' }}</h3>
            <p v-for="reason in task.trace.review_reasons" :key="reason" class="review-reason">{{ reason }}</p>
            <label>教师总评（确认后写回 Word）</label>
            <textarea v-model="reviewNote" :disabled="completed" rows="5"></textarea>
            <button
              v-if="!completed && reviewTarget"
              class="quick-adjust"
              type="button"
              @click="applyTeacherAdjustment"
            >
              应用教师调整 · {{ reviewTarget.criterion_name }}
              {{ teacherAdjustment.from }} → {{ teacherAdjustment.to }}
            </button>
            <button class="primary-btn review-btn" :disabled="reviewing || completed" @click="submitReview">
              {{ completed ? '已确认并发布' : reviewing ? '提交中…' : '确认调整并发布' }}
            </button>
            <div class="guardrail">
              <strong>教学边界</strong>
              <span>AI 只生成辅助建议；正式成绩由教师确认。上传材料 24 小时自动删除，也可立即删除。</span>
            </div>
            <div v-if="completed" class="download-links">
              <a :href="labTraceDownloadUrl(task.task_id, 'report')">下载可编辑批注 Word ↗</a>
              <a :href="labTraceDownloadUrl(task.task_id, 'trace')">下载证据链 JSON ↗</a>
              <button type="button" :disabled="deleting" @click="deleteTaskData">
                {{ deleting ? '正在删除…' : '立即删除本次数据' }}
              </button>
            </div>
          </aside>
        </div>

        <div v-if="completed && task.diagnosis" class="diagnosis-panel">
          <div>
            <p class="eyebrow">CLASS DIAGNOSIS</p>
            <h2>从一份批改，走向下一次教学</h2>
            <p>仅聚合教师已复核记录；未复核建议不进入班级统计。</p>
          </div>
          <div class="diagnosis-stats">
            <div>
              <b>{{ task.diagnosis.record_count }}</b>
              <span>已复核样本</span>
            </div>
            <div>
              <b>{{ task.diagnosis.class_average }}</b>
              <span>班级均分</span>
            </div>
            <div>
              <b>{{ Math.round((task.diagnosis.top_weaknesses[0]?.average_rate || 0) * 100) }}%</b>
              <span>最弱维度达成率</span>
            </div>
          </div>
          <div class="teaching-actions">
            <span v-for="(item, index) in task.diagnosis.top_weaknesses" :key="item.criterion_id">
              0{{ index + 1 }} · {{ item.teacher_action }}
            </span>
          </div>
        </div>
      </section>

      <footer>
        <span>格物智评 LabTrace · 独立变量</span>
        <span>可追溯 · 可复核 · 可复现 · 可迁移</span>
      </footer>
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #f2f0e9;
}

.labtrace-page {
  --ink: #15231f;
  --forest: #174d40;
  --mint: #1b8b73;
  --orange: #dc633f;
  --paper: #f7f5ee;
  --line: rgba(21, 35, 31, .14);
  min-height: 100vh;
  color: var(--ink);
  background:
    radial-gradient(circle at 83% 8%, rgba(220, 99, 63, .13), transparent 23rem),
    linear-gradient(rgba(23, 77, 64, .035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(23, 77, 64, .035) 1px, transparent 1px),
    #f2f0e9;
  background-size: auto, 32px 32px, 32px 32px, auto;
  font-family: Inter, "PingFang SC", "Noto Sans SC", sans-serif;
}

.topbar {
  height: 74px;
  padding: 0 clamp(24px, 5vw, 76px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line);
  background: rgba(242, 240, 233, .88);
  backdrop-filter: blur(16px);
  position: sticky;
  top: 0;
  z-index: 20;
}

.brand { display: flex; align-items: center; gap: 12px; color: inherit; text-decoration: none; }
.brand-mark { width: 38px; height: 38px; display: grid; place-items: center; background: var(--forest); color: #fff; border-radius: 50%; font-family: serif; font-size: 20px; }
.brand strong, .brand small { display: block; }
.brand strong { font-size: 16px; letter-spacing: .02em; }
.brand strong em { color: var(--mint); font-style: normal; }
.brand small { margin-top: 2px; color: #68756f; font-size: 10px; letter-spacing: .12em; }
.top-meta { display: flex; align-items: center; gap: 10px; color: #66736e; font-size: 12px; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #2da77f; box-shadow: 0 0 0 5px rgba(45, 167, 127, .1); }
.top-rule { width: 1px; height: 14px; background: var(--line); margin: 0 4px; }

main { overflow: hidden; }
.hero, .workflow, .workbench, .result-section, footer { width: min(1180px, calc(100% - 48px)); margin-inline: auto; }
.hero { min-height: 610px; display: grid; grid-template-columns: 1.3fr .7fr; align-items: center; gap: 80px; padding: 54px 0 40px; }
.eyebrow { margin: 0 0 18px; color: var(--orange); font: 700 11px/1.2 "DM Sans", sans-serif; letter-spacing: .2em; }
.hero h1 { margin: 0; font: 600 clamp(46px, 6vw, 78px)/1.03 Georgia, "Songti SC", serif; letter-spacing: -.045em; }
.hero h1 span { color: var(--forest); }
.hero-lead { max-width: 640px; margin: 28px 0 0; color: #52615b; font-size: 17px; line-height: 1.85; }
.hero-actions { display: flex; align-items: center; gap: 25px; margin-top: 36px; }
.primary-btn, .secondary-btn { border: 0; border-radius: 3px; cursor: pointer; font-weight: 700; transition: .2s ease; }
.primary-btn { padding: 14px 22px; color: #fff; background: var(--forest); box-shadow: 0 8px 24px rgba(23, 77, 64, .16); }
.primary-btn:hover { background: #0f3e33; transform: translateY(-1px); }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; transform: none; }
.secondary-btn { padding: 12px 18px; color: var(--forest); border: 1px solid var(--line); background: transparent; }
.text-link { color: var(--ink); text-decoration: none; font-weight: 700; font-size: 14px; }
.text-link span { color: var(--orange); font-size: 18px; }

.hero-card { padding: 29px; background: var(--ink); color: #fff; border-radius: 4px; box-shadow: 22px 22px 0 rgba(220, 99, 63, .15); transform: rotate(1deg); }
.card-label, .panel-kicker { color: #9bb1a9; font: 700 10px/1 "DM Sans", sans-serif; letter-spacing: .18em; }
.mode-title { display: flex; align-items: center; gap: 15px; margin-top: 20px; }
.mode-icon { width: 48px; height: 48px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.18); border-radius: 50%; color: #f18965; font-size: 28px; }
.mode-title strong, .mode-title small { display: block; }
.mode-title strong { font-size: 18px; }
.mode-title small { margin-top: 5px; color: #97aaa3; font-size: 11px; }
.hero-card > p { margin: 24px 0; color: #bfcbc7; font-size: 13px; line-height: 1.75; }
.mode-grid { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid rgba(255,255,255,.13); padding-top: 20px; }
.mode-grid b, .mode-grid span { display: block; }
.mode-grid b { font: 600 27px/1 Georgia, serif; color: #f18965; }
.mode-grid span { margin-top: 6px; color: #93a69f; font-size: 10px; }

.workflow { padding: 90px 0; border-top: 1px solid var(--line); }
.section-heading { display: grid; grid-template-columns: .45fr 1fr .8fr; gap: 40px; align-items: end; }
.section-heading h2, .workbench h2, .diagnosis-panel h2 { margin: 0; font: 600 34px/1.2 Georgia, "Songti SC", serif; }
.section-heading > p:last-child { color: #65726d; line-height: 1.7; margin: 0; }
.step-rail { display: grid; grid-template-columns: repeat(6, 1fr); margin-top: 52px; border-top: 1px solid var(--ink); }
.step-item { padding: 19px 16px 0 0; position: relative; }
.step-item::before { content: ""; position: absolute; width: 7px; height: 7px; border-radius: 50%; background: var(--orange); top: -4px; left: 0; }
.step-number { display: block; color: var(--orange); font: 700 11px/1 "DM Sans", sans-serif; }
.step-item strong, .step-item small { display: block; }
.step-item strong { margin-top: 14px; font-size: 15px; }
.step-item small { margin-top: 7px; color: #718079; line-height: 1.5; }

.workbench { padding: 72px 0 86px; }
.workbench-head { display: flex; align-items: end; justify-content: space-between; gap: 30px; }
.privacy-pill { padding: 8px 12px; color: var(--mint); border: 1px solid rgba(27,139,115,.3); border-radius: 30px; font-size: 11px; }
.fixture-strip { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 30px; padding: 20px 22px; color: #fff; background: var(--forest); border-left: 4px solid var(--orange); }
.fixture-strip strong, .fixture-strip small { display: block; }
.fixture-strip strong { margin-top: 7px; font: 600 17px/1.25 Georgia, "Songti SC", serif; }
.fixture-strip small { margin-top: 6px; color: #b8cbc4; font-size: 11px; line-height: 1.55; }
.template-download { flex: 0 0 auto; padding: 11px 15px; color: #fff; border: 1px solid rgba(255,255,255,.28); text-decoration: none; font-size: 12px; font-weight: 700; }
.template-download:hover { color: #fff; border-color: #f3a185; background: rgba(255,255,255,.08); }
.fixture-strip .rubric-label { color: #f3a185; }
.sample-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 14px; }
.sample-option { padding: 18px; text-align: left; color: var(--ink); border: 1px solid var(--line); background: rgba(255,255,255,.42); cursor: pointer; transition: .2s ease; }
.sample-option:hover, .sample-option.active { border-color: var(--forest); background: #fff; transform: translateY(-2px); }
.sample-option span, .sample-option strong, .sample-option small { display: block; }
.sample-option span { color: var(--orange); font-size: 10px; font-weight: 800; letter-spacing: .14em; }
.sample-option strong { margin-top: 9px; font-size: 15px; }
.sample-option small { margin-top: 7px; color: #6d7a74; line-height: 1.5; }
.upload-panel { display: grid; grid-template-columns: auto 1fr auto auto; gap: 18px; align-items: center; margin-top: 34px; padding: 24px; border: 1px dashed rgba(21,35,31,.3); background: rgba(255,255,255,.4); }
.upload-panel.ready { border-style: solid; border-color: rgba(27,139,115,.45); background: rgba(255,255,255,.67); }
.file-icon { width: 54px; height: 62px; border: 0; color: #fff; background: var(--orange); clip-path: polygon(0 0, 75% 0, 100% 22%, 100% 100%, 0 100%); font: 800 11px/1 "DM Sans", sans-serif; cursor: pointer; }
.file-copy strong, .file-copy span { display: block; }
.file-copy strong { font-size: 15px; }
.file-copy span { margin-top: 6px; color: #7a8782; font-size: 12px; }
.run-btn { min-width: 160px; }
.rubric-panel { display: grid; grid-template-columns: 1fr auto auto; gap: 18px; align-items: center; padding: 18px 24px; border: 1px solid var(--line); border-top: 0; background: rgba(255,255,255,.56); }
.rubric-panel > div strong, .rubric-panel > div small { display: block; }
.rubric-panel > div strong { margin-top: 5px; font-size: 14px; }
.rubric-panel > div small { margin-top: 4px; color: #76837e; font-size: 11px; }
.rubric-label { color: var(--orange); font: 800 9px/1 "DM Sans", sans-serif; letter-spacing: .16em; }
.rubric-template { color: var(--forest); font-size: 11px; font-weight: 700; text-decoration: none; }
.data-notice { display: flex; gap: 13px; margin-top: 14px; padding: 13px 17px; color: #56665f; border-left: 3px solid var(--mint); background: rgba(27,139,115,.07); font-size: 11px; line-height: 1.55; }
.data-notice strong { flex: 0 0 auto; color: var(--forest); }
.data-notice > div > span { display: block; }
.image-consent { display: flex; align-items: flex-start; gap: 7px; margin-top: 8px; color: #8b4a34; cursor: pointer; }
.image-consent input { margin-top: 2px; accent-color: var(--orange); }
.running-panel { margin-top: 14px; padding: 24px; display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 17px; background: var(--ink); color: #fff; position: relative; overflow: hidden; }
.running-panel p { margin: 5px 0 0; color: #96aaa2; font-size: 12px; }
.scan-orbit { width: 34px; height: 34px; border: 1px solid rgba(255,255,255,.2); border-radius: 50%; animation: spin 1.4s linear infinite; }
.scan-orbit span { display: block; width: 7px; height: 7px; background: #f18965; border-radius: 50%; }
.progress-line { position: absolute; left: 0; bottom: 0; width: 100%; height: 3px; background: rgba(255,255,255,.1); }
.progress-line span { display: block; width: 42%; height: 100%; background: var(--orange); animation: progress 1.4s ease-in-out infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes progress { 0% { transform: translateX(-100%); } 100% { transform: translateX(340%); } }

.result-section { padding: 80px 0; border-top: 1px solid var(--line); }
.result-header { display: flex; justify-content: space-between; align-items: end; padding-bottom: 34px; }
.result-header h2 { margin: 0; font: 600 34px/1 Georgia, serif; }
.result-header h2 span { color: var(--orange); font-size: 66px; }
.result-header h2 small { color: #82908b; font-size: 18px; }
.result-header > div > p:last-child { color: #6a7772; }
.run-badges { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
.run-badges span { padding: 5px 8px; color: var(--forest); border: 1px solid rgba(23,77,64,.2); background: rgba(255,255,255,.48); font-size: 9px; font-weight: 700; letter-spacing: .03em; }
.run-badges span.fallback { color: #9f4529; border-color: rgba(220,99,63,.35); background: rgba(220,99,63,.08); }
.profile { display: flex; gap: 36px; }
.profile b, .profile span { display: block; text-align: right; }
.profile b { font: 600 25px/1 Georgia, serif; }
.profile span { margin-top: 5px; color: #75827d; font-size: 10px; }
.word-delivery-banner { margin-bottom: 24px; padding: 22px 24px; display: flex; align-items: center; justify-content: space-between; gap: 28px; color: #fff; background: var(--forest); border-left: 5px solid var(--orange); }
.word-delivery-banner > div:first-child span, .word-delivery-banner > div:first-child strong { display: block; }
.word-delivery-banner > div:first-child span { color: #9fc1b5; font: 700 9px/1 "DM Sans", sans-serif; letter-spacing: .16em; }
.word-delivery-banner > div:first-child strong { margin-top: 8px; font: 600 19px/1.25 Georgia, "Songti SC", serif; }
.delivery-facts { display: flex; align-items: center; gap: 22px; }
.delivery-facts span { color: #b9cbc5; font-size: 10px; white-space: nowrap; }
.delivery-facts b { display: block; margin-bottom: 5px; color: #f3a185; font: 600 20px/1 Georgia, serif; }
.result-grid { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 26px; align-items: start; }
.criteria-panel { background: #fff; border: 1px solid var(--line); }
.panel-title { padding: 21px 24px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--line); }
.panel-title h3 { margin: 0; font-size: 16px; }
.panel-title span { color: #74817c; font-size: 11px; }
.criterion-card { padding: 21px 24px; border-bottom: 1px solid var(--line); position: relative; }
.criterion-card:last-child { border-bottom: 0; }
.criterion-card.uncertain { background: #fff8f2; }
.criterion-card.uncertain::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--orange); }
.criterion-score { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.criterion-score > span { font-weight: 700; }
.criterion-score input { width: 52px; padding: 5px; text-align: center; border: 1px solid var(--line); color: var(--forest); font-weight: 800; font-size: 17px; }
.criterion-score small { color: #8a9691; }
.criterion-card > p { margin: 9px 0; color: #55645e; line-height: 1.6; font-size: 13px; }
.criterion-meta { display: flex; gap: 10px; color: var(--mint); font-size: 10px; }
.criterion-meta .warning, .review-flag { color: var(--orange); }
.review-flag { font-weight: 800; }
.evidence-list { margin-top: 12px; display: grid; gap: 7px; }
.evidence-row { display: grid; grid-template-columns: 128px 1fr; gap: 10px; padding: 8px 10px; background: #f4f6f3; font-size: 11px; }
.locator { color: var(--mint); font: 700 10px/1.5 "DM Sans", monospace; }
.evidence-row q { display: block; color: #60706a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evidence-row small { display: block; margin-top: 5px; color: #9a5a43; font-size: 9px; font-weight: 700; }
.evidence-row small.observed { color: var(--mint); }

.review-panel { padding: 26px; background: var(--ink); color: #fff; position: sticky; top: 98px; }
.review-panel h3 { margin: 16px 0; font: 600 23px/1.25 Georgia, "Songti SC", serif; }
.review-reason { padding: 12px; color: #d9c4b9; border-left: 2px solid var(--orange); background: rgba(220,99,63,.09); font-size: 12px; line-height: 1.55; }
.review-panel label { display: block; margin: 20px 0 8px; color: #9eb0aa; font-size: 11px; }
.review-panel textarea { width: 100%; box-sizing: border-box; padding: 11px; resize: vertical; color: #e9efec; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15); font: inherit; font-size: 12px; line-height: 1.55; }
.quick-adjust { width: 100%; margin-top: 10px; padding: 10px 9px; color: #f4a384; border: 1px solid rgba(244,163,132,.4); background: transparent; font-size: 11px; cursor: pointer; }
.review-btn { width: 100%; margin-top: 12px; background: var(--orange); }
.guardrail { margin-top: 23px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.13); }
.guardrail strong, .guardrail span { display: block; }
.guardrail strong { color: #f18965; font-size: 11px; }
.guardrail span { margin-top: 7px; color: #92a59e; font-size: 11px; line-height: 1.55; }
.download-links { display: grid; gap: 8px; margin-top: 18px; }
.download-links a, .download-links button { padding: 0; color: #f4a384; border: 0; background: transparent; font: inherit; font-size: 12px; text-align: left; text-decoration: none; cursor: pointer; }

.diagnosis-panel { margin-top: 30px; padding: 38px; display: grid; grid-template-columns: 1.15fr .8fr 1fr; gap: 42px; align-items: center; background: #dfe9e1; }
.diagnosis-panel > div > p:last-child { color: #607069; line-height: 1.6; }
.diagnosis-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.diagnosis-stats div { padding: 15px 8px; text-align: center; border-left: 1px solid rgba(21,35,31,.13); }
.diagnosis-stats b, .diagnosis-stats span { display: block; }
.diagnosis-stats b { color: var(--forest); font: 600 26px/1 Georgia, serif; }
.diagnosis-stats span { margin-top: 8px; color: #6b7973; font-size: 9px; }
.teaching-actions { display: grid; gap: 9px; }
.teaching-actions span { padding: 10px 12px; background: rgba(255,255,255,.55); font-size: 11px; line-height: 1.45; }

footer { padding: 28px 0 44px; display: flex; justify-content: space-between; color: #6c7974; border-top: 1px solid var(--line); font-size: 11px; letter-spacing: .08em; }

@media (max-width: 900px) {
  .hero { grid-template-columns: 1fr; gap: 36px; padding-top: 75px; }
  .hero-card { transform: none; }
  .section-heading { grid-template-columns: 1fr; gap: 14px; }
  .step-rail { grid-template-columns: repeat(2, 1fr); row-gap: 35px; }
  .sample-grid { grid-template-columns: 1fr; }
  .fixture-strip { align-items: flex-start; flex-direction: column; }
  .upload-panel { grid-template-columns: auto 1fr; }
  .rubric-panel { grid-template-columns: 1fr auto; }
  .upload-panel .secondary-btn, .upload-panel .run-btn { width: 100%; }
  .result-grid { grid-template-columns: 1fr; }
  .word-delivery-banner { align-items: flex-start; flex-direction: column; }
  .review-panel { position: static; }
  .diagnosis-panel { grid-template-columns: 1fr; }
}

@media (max-width: 600px) {
  .top-meta { display: none; }
  .hero, .workflow, .workbench, .result-section, footer { width: min(100% - 28px, 1180px); }
  .hero h1 { font-size: 42px; }
  .hero-actions, .workbench-head, .result-header, .profile, footer { align-items: flex-start; flex-direction: column; }
  .step-rail { grid-template-columns: 1fr; }
  .upload-panel { grid-template-columns: 1fr; }
  .rubric-panel { grid-template-columns: 1fr; }
  .data-notice { flex-direction: column; }
  .profile { gap: 14px; }
  .delivery-facts { flex-wrap: wrap; }
  .profile b, .profile span { text-align: left; }
  .evidence-row { grid-template-columns: 1fr; }
}
</style>
