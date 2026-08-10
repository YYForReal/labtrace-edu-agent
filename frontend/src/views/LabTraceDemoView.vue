<script setup lang="ts">
import { computed, nextTick, onMounted, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  deleteLabTraceTask,
  getLabTraceBootstrap,
  getLabTraceTask,
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
const docxContainer = ref<HTMLElement | null>(null)
const docxPreviewModule = shallowRef<any>(null)
const previewLoading = ref(false)
const previewError = ref('')
const previewKind = ref<'source' | 'report'>('report')
const activeEvidenceId = ref('')
let previewSequence = 0

const totalScore = computed(() => {
  if (!task.value) return 0
  return task.value.trace.criteria.reduce((sum, item) => sum + Number(item.score || 0), 0)
})

const evidenceMap = computed(() => {
  const result: Record<string, LabTraceTask['trace']['evidence'][number]> = {}
  for (const item of task.value?.trace.evidence || []) result[item.evidence_id] = item
  return result
})

const citationByEvidence = computed(() => {
  const result: Record<string, LabTraceTask['evidence_appendix'][number]> = {}
  for (const item of task.value?.evidence_appendix || []) result[item.evidence_id] = item
  return result
})

const wordCommentByCriterion = computed(() => {
  const result: Record<string, LabTraceTask['word_comments'][number]> = {}
  for (const item of task.value?.word_comments || []) result[item.criterion_id] = item
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

async function renderWordPreview(kind: 'source' | 'report' = previewKind.value) {
  if (!task.value?.word_workflow.input_is_word) return
  previewKind.value = kind
  previewLoading.value = true
  previewError.value = ''
  activeEvidenceId.value = ''
  const sequence = ++previewSequence
  await nextTick()
  const container = docxContainer.value
  if (container) container.innerHTML = ''
  try {
    if (!docxPreviewModule.value) docxPreviewModule.value = await import('docx-preview')
    const response = await fetch(labTraceDownloadUrl(task.value.task_id, kind), {
      cache: 'no-cache',
    })
    if (!response.ok) throw new Error(`Word 预览加载失败（HTTP ${response.status}）`)
    const blob = await response.blob()
    if (sequence !== previewSequence || !container) return
    await docxPreviewModule.value.renderAsync(blob, container, undefined, {
      className: 'labtrace-docx',
      inWrapper: true,
      ignoreWidth: false,
      ignoreHeight: false,
      useBase64URL: true,
      breakPages: true,
      experimental: true,
    })
  } catch (error: any) {
    if (sequence === previewSequence) previewError.value = error?.message || 'Word 预览加载失败'
  } finally {
    if (sequence === previewSequence) previewLoading.value = false
  }
}

function normalizePreviewText(value: string | null | undefined) {
  return String(value || '').replace(/\s+/g, ' ').trim()
}

function focusEvidence(evidenceId: string) {
  const evidence = evidenceMap.value[evidenceId]
  const root = docxContainer.value
  if (!evidence || !root) return
  activeEvidenceId.value = evidenceId
  root.querySelectorAll('.labtrace-evidence-highlight').forEach((element) => {
    element.classList.remove('labtrace-evidence-highlight')
  })

  let target: HTMLElement | undefined
  // Tables and images have unambiguous structural locators. Resolve them before
  // excerpt matching so the copy repeated in the generated appendix is not selected.
  if (evidence.kind === 'table') {
    const match = evidence.locator.match(/table:(\d+)/)
    const tables = Array.from(root.querySelectorAll<HTMLElement>('table'))
    if (match) target = tables[Number(match[1]) - 1]
  }
  if (['image', 'image_context', 'chart'].includes(evidence.kind)) {
    const match = evidence.locator.match(/image:(\d+)/)
    const images = Array.from(root.querySelectorAll<HTMLElement>('img'))
    if (match) target = images[Number(match[1]) - 1]
  }
  if (!target) {
    const candidates = Array.from(root.querySelectorAll<HTMLElement>('p, td, th'))
    const excerpt = normalizePreviewText(evidence.excerpt)
    const needle = excerpt.slice(0, Math.min(24, excerpt.length))
    target = needle
      ? candidates.find(element => normalizePreviewText(element.textContent).includes(needle))
      : undefined
  }
  if (!target) {
    const match = evidence.locator.match(/paragraph:(\d+)/)
    const paragraphs = Array.from(root.querySelectorAll<HTMLElement>('p'))
    if (match) target = paragraphs[Number(match[1]) - 1]
  }

  if (target) {
    target.classList.add('labtrace-evidence-highlight')
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  } else {
    ElMessage.info(`${citationByEvidence.value[evidenceId]?.citation || evidenceId} 已定位到 ${citationByEvidence.value[evidenceId]?.location_label || evidence.locator}`)
  }
}

async function openTeacherConsole() {
  if (!task.value) {
    ElMessage.info('请先载入样例并运行批改 Agent，随后即可进入教师管理台。')
    document.querySelector('.workbench')?.scrollIntoView({ behavior: 'smooth' })
    return
  }
  window.history.replaceState(null, '', '#teacher-console')
  await nextTick()
  document.querySelector('#teacher-console')?.scrollIntoView({ behavior: 'smooth' })
  if (!docxContainer.value?.childElementCount) await renderWordPreview('report')
}

onMounted(async () => {
  try {
    bootstrap.value = (await getLabTraceBootstrap()).data
    const storedTaskId = sessionStorage.getItem('labtrace-teacher-task')
    if (window.location.hash === '#teacher-console' && storedTaskId) {
      task.value = (await getLabTraceTask(storedTaskId)).data
      reviewSuggestionScore.value = Number(reviewTarget.value?.score || 0)
      await nextTick()
      await renderWordPreview('report')
    }
  } catch {
    ElMessage.error('演示服务尚未启动，请按运行说明启动后刷新页面。')
  }
})

function chooseFile(event: Event) {
  const files = (event.target as HTMLInputElement).files
  selectedFile.value = files?.[0] || null
  task.value = null
  previewError.value = ''
  if (docxContainer.value) docxContainer.value.innerHTML = ''
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
    previewError.value = ''
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
    sessionStorage.setItem('labtrace-teacher-task', task.value.task_id)
    reviewSuggestionScore.value = Number(reviewTarget.value?.score || 0)
    reviewNote.value = `已核对证据定位与评分标准；将“${reviewTarget.value?.criterion_name || '待复核维度'}”从 ${teacherAdjustment.value.from} 分调整为 ${teacherAdjustment.value.to} 分后确认发布。`
    ElMessage.success(
      task.value.mode === 'model_agent'
        ? '真实模型建议与证据链已生成，现已转交教师终审'
        : '证据链已生成；本次使用可复现规则或显式降级路径',
    )
    await nextTick()
    await renderWordPreview('report')
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
    sessionStorage.setItem('labtrace-teacher-task', task.value.task_id)
    await nextTick()
    await renderWordPreview('report')
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
    sessionStorage.removeItem('labtrace-teacher-task')
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
    if (docxContainer.value) docxContainer.value.innerHTML = ''
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
      <div class="top-actions">
        <button class="teacher-entry" type="button" @click="openTeacherConsole">
          教师管理台
          <span v-if="task">{{ completed ? '已终审' : '待处理 1' }}</span>
        </button>
        <div class="top-meta">
          <span class="live-dot"></span>
          <span>{{ bootstrap?.mode.external_processing ? '真实模型在线' : '可离线复现' }}</span>
          <span class="top-rule"></span>
          <span>GOAI 2026 · AI+教育</span>
        </div>
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

        <div id="teacher-console" class="teacher-console-shell">
          <header class="console-header">
            <div>
              <span class="console-kicker">TEACHER REVIEW DESK</span>
              <h3>教师管理台 · 原文、批注、评分同屏复核</h3>
            </div>
            <div class="console-status">
              <span>{{ task.input_filename }}</span>
              <b :class="{ done: completed }">{{ completed ? '已终审' : '待教师确认' }}</b>
            </div>
          </header>

          <div class="teacher-console-grid">
            <section class="report-preview-panel">
              <div class="report-toolbar">
                <div>
                  <strong>Word 报告预览</strong>
                  <span>点击右侧 [n] 引用，可回到对应段落、表格或图片</span>
                </div>
                <div class="preview-switch" role="group" aria-label="Word 版本">
                  <button
                    type="button"
                    :class="{ active: previewKind === 'source' }"
                    @click="renderWordPreview('source')"
                  >原始报告</button>
                  <button
                    type="button"
                    :class="{ active: previewKind === 'report' }"
                    @click="renderWordPreview('report')"
                  >批改版 Word</button>
                </div>
              </div>
              <div class="report-preview-scroll">
                <div v-if="previewLoading" class="preview-placeholder">
                  <span class="preview-spinner"></span>
                  正在还原 Word 图文版式…
                </div>
                <div v-else-if="previewError" class="preview-placeholder error">{{ previewError }}</div>
                <div
                  v-show="!previewLoading && !previewError"
                  ref="docxContainer"
                  class="docx-host"
                ></div>
              </div>
            </section>

            <aside class="teacher-score-panel">
              <div class="score-panel-head">
                <div>
                  <span>{{ completed ? '最终成绩' : 'Agent 建议分' }}</span>
                  <strong>{{ totalScore }}<small>/{{ task.rubric.total_score }}</small></strong>
                </div>
                <div>
                  <b>{{ task.word_comments.length }}</b>
                  <span>Word 批注</span>
                </div>
                <div>
                  <b>{{ task.evidence_appendix.length }}</b>
                  <span>引用证据</span>
                </div>
              </div>

              <div class="score-card-list">
                <article
                  v-for="criterion in task.trace.criteria"
                  :key="criterion.criterion_id"
                  class="criterion-card"
                  :class="{ uncertain: criterion.confidence < 0.75 }"
                >
                  <div class="criterion-score">
                    <span>{{ criterion.criterion_name }}</span>
                    <div>
                      <input v-model.number="criterion.score" :disabled="completed" :max="criterion.max_score" min="0" step="0.5" type="number">
                      <small>/ {{ criterion.max_score }}</small>
                    </div>
                  </div>
                  <p>{{ criterion.reason }}</p>
                  <div class="criterion-meta">
                    <span :class="{ warning: criterion.confidence < 0.75 }">
                      置信度 {{ Math.round(criterion.confidence * 100) }}%
                    </span>
                    <span v-if="wordCommentByCriterion[criterion.criterion_id]" class="comment-badge">
                      {{ wordCommentByCriterion[criterion.criterion_id].comment_id }} · Word 原生批注
                    </span>
                  </div>
                  <div class="citation-links" aria-label="关联证据">
                    <button
                      v-for="id in criterion.evidence_ids"
                      :key="id"
                      type="button"
                      :class="{ active: activeEvidenceId === id }"
                      @click="focusEvidence(id)"
                    >
                      <b>{{ citationByEvidence[id]?.citation || id }}</b>
                      <span>{{ citationByEvidence[id]?.location_label || evidenceMap[id]?.locator }}</span>
                    </button>
                  </div>
                </article>
              </div>

              <div class="review-box">
                <div class="panel-kicker">HUMAN-IN-THE-LOOP</div>
                <h3>{{ completed ? '教师终审已完成' : '确认低置信度判断' }}</h3>
                <details v-if="task.trace.review_reasons.length" class="review-reasons-box">
                  <summary>{{ task.trace.review_reasons.length }} 项复核提醒</summary>
                  <p v-for="reason in task.trace.review_reasons" :key="reason">{{ reason }}</p>
                </details>
                <label>教师总评（确认后写回 Word）</label>
                <textarea v-model="reviewNote" :disabled="completed" rows="4"></textarea>
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
                  <a :href="labTraceDownloadUrl(task.task_id, 'trace')">下载含附录的证据链 JSON ↗</a>
                  <button type="button" :disabled="deleting" @click="deleteTaskData">
                    {{ deleting ? '正在删除…' : '立即删除本次数据' }}
                  </button>
                </div>
              </div>
            </aside>
          </div>
        </div>

        <section class="evidence-appendix">
          <div class="appendix-head">
            <div>
              <p class="eyebrow">EVIDENCE APPENDIX</p>
              <h3>附录 · 科研式证据引用索引</h3>
              <p>评分理由与 Word 批注统一使用 [n]；内部 p-/t-/i- 编号保留用于工程追溯。</p>
            </div>
            <span>{{ task.evidence_appendix.length }} REFERENCES</span>
          </div>
          <button
            v-for="reference in task.evidence_appendix"
            :key="reference.evidence_id"
            type="button"
            class="appendix-entry"
            :class="{ active: activeEvidenceId === reference.evidence_id }"
            @click="focusEvidence(reference.evidence_id)"
          >
            <b>{{ reference.citation }}</b>
            <div class="appendix-locator">
              <code>{{ reference.evidence_id }}</code>
              <span>{{ reference.location_label }}</span>
              <small>{{ reference.kind_label }}</small>
            </div>
            <p>{{ reference.excerpt }}</p>
            <div class="appendix-linked">
              <span v-for="name in reference.linked_criteria" :key="name">{{ name }}</span>
            </div>
          </button>
        </section>

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
.top-actions { display: flex; align-items: center; gap: 18px; }
.teacher-entry { display: flex; align-items: center; gap: 8px; padding: 9px 12px; color: var(--forest); border: 1px solid rgba(23,77,64,.24); background: rgba(255,255,255,.52); font: 700 11px/1 "DM Sans", sans-serif; cursor: pointer; }
.teacher-entry:hover { color: #fff; background: var(--forest); }
.teacher-entry span { padding: 3px 5px; color: #fff; background: var(--orange); font-size: 8px; }
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #2da77f; box-shadow: 0 0 0 5px rgba(45, 167, 127, .1); }
.top-rule { width: 1px; height: 14px; background: var(--line); margin: 0 4px; }

main { overflow-x: clip; }
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

.result-section { width: min(1480px, calc(100% - 48px)); padding: 80px 0; border-top: 1px solid var(--line); }
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
.teacher-console-shell { min-width: 0; border: 1px solid var(--line); background: rgba(255,255,255,.58); }
.console-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 19px 22px; border-bottom: 1px solid var(--line); background: #fff; }
.console-kicker { color: var(--orange); font: 800 9px/1 "DM Sans", sans-serif; letter-spacing: .17em; }
.console-header h3 { margin: 7px 0 0; font: 600 20px/1.2 Georgia, "Songti SC", serif; }
.console-status { min-width: 0; display: flex; align-items: center; gap: 10px; color: #6d7a75; font-size: 11px; }
.console-status span { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.console-status b { flex: 0 0 auto; padding: 6px 8px; color: #9d472e; border: 1px solid rgba(220,99,63,.35); background: rgba(220,99,63,.08); font-size: 10px; }
.console-status b.done { color: var(--mint); border-color: rgba(27,139,115,.3); background: rgba(27,139,115,.07); }
.teacher-console-grid { min-width: 0; display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(360px, .75fr); gap: 0; height: 820px; }
.report-preview-panel, .teacher-score-panel { min-width: 0; min-height: 0; }
.report-preview-panel { display: flex; flex-direction: column; border-right: 1px solid var(--line); background: #e8ebe7; }
.report-toolbar { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 13px 16px; border-bottom: 1px solid var(--line); background: #f9faf8; }
.report-toolbar strong, .report-toolbar span { display: block; }
.report-toolbar strong { font-size: 13px; }
.report-toolbar span { margin-top: 3px; color: #718079; font-size: 9px; }
.preview-switch { flex: 0 0 auto; display: flex; padding: 3px; background: #e8ece8; }
.preview-switch button { padding: 7px 10px; color: #63706b; border: 0; background: transparent; font-size: 10px; font-weight: 700; cursor: pointer; }
.preview-switch button.active { color: #fff; background: var(--forest); }
.report-preview-scroll { min-width: 0; min-height: 0; flex: 1; overflow: auto; overscroll-behavior: contain; }
.preview-placeholder { min-height: 420px; display: flex; align-items: center; justify-content: center; gap: 10px; color: #73817b; font-size: 12px; }
.preview-placeholder.error { color: #a4482d; }
.preview-spinner { width: 18px; height: 18px; border: 2px solid rgba(23,77,64,.16); border-top-color: var(--forest); border-radius: 50%; animation: spin .8s linear infinite; }
.docx-host { min-width: 0; min-height: 100%; }
.docx-host :deep(.docx-wrapper),
.docx-host :deep(.labtrace-docx-wrapper) { padding: 22px 12px !important; background: #e8ebe7 !important; }
.docx-host :deep(.labtrace-docx) { max-width: 100%; margin: 0 auto 22px !important; box-shadow: 0 8px 30px rgba(21,35,31,.15) !important; }
.docx-host :deep(.labtrace-evidence-highlight) { outline: 3px solid rgba(220,99,63,.78) !important; outline-offset: 4px; background: rgba(255,225,130,.34) !important; transition: outline-color .2s ease; }
.teacher-score-panel { display: flex; flex-direction: column; color: #fff; background: var(--ink); overflow: hidden; }
.score-panel-head { flex: 0 0 auto; display: grid; grid-template-columns: 1.25fr .7fr .7fr; border-bottom: 1px solid rgba(255,255,255,.12); }
.score-panel-head > div { padding: 15px 14px; border-right: 1px solid rgba(255,255,255,.1); }
.score-panel-head > div:last-child { border-right: 0; }
.score-panel-head span, .score-panel-head b, .score-panel-head strong { display: block; }
.score-panel-head span { color: #8fa39b; font-size: 9px; }
.score-panel-head strong { margin-top: 4px; color: #f3a185; font: 600 29px/1 Georgia, serif; }
.score-panel-head strong small { color: #91a49d; font-size: 12px; }
.score-panel-head b { margin-bottom: 5px; color: #f3a185; font: 600 20px/1 Georgia, serif; }
.score-card-list { min-height: 0; flex: 1 1 auto; overflow-y: auto; overscroll-behavior: contain; }
.score-card-list .criterion-card { border-color: rgba(255,255,255,.1); background: transparent; }
.score-card-list .criterion-card.uncertain { background: rgba(220,99,63,.09); }
.score-card-list .criterion-score > span { color: #f2f6f4; }
.score-card-list .criterion-score input { color: #fff; border-color: rgba(255,255,255,.2); background: rgba(255,255,255,.08); }
.score-card-list .criterion-score input:disabled { opacity: .7; }
.score-card-list .criterion-card > p { color: #b8c5c0; overflow-wrap: anywhere; word-break: break-word; }
.comment-badge { color: #f3a185 !important; }
.citation-links { min-width: 0; display: grid; gap: 6px; margin-top: 11px; }
.citation-links button { min-width: 0; width: 100%; display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 8px; align-items: center; padding: 7px 9px; color: #b8c7c1; border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.04); text-align: left; cursor: pointer; }
.citation-links button:hover, .citation-links button.active { border-color: #f3a185; background: rgba(243,161,133,.1); }
.citation-links b { color: #f3a185; font: 700 11px/1 "DM Sans", sans-serif; }
.citation-links span { min-width: 0; overflow-wrap: anywhere; font-size: 9px; line-height: 1.4; }
.review-box { flex: 0 0 auto; padding: 17px 20px 20px; border-top: 1px solid rgba(255,255,255,.12); background: #10211c; }
.review-box h3 { margin: 8px 0 10px; font: 600 18px/1.2 Georgia, "Songti SC", serif; }
.review-reasons-box { margin-bottom: 10px; color: #d7c5bd; font-size: 10px; }
.review-reasons-box summary { color: #f3a185; cursor: pointer; }
.review-reasons-box p { margin: 8px 0; padding-left: 8px; border-left: 2px solid var(--orange); line-height: 1.5; overflow-wrap: anywhere; }
.review-box label { display: block; margin: 8px 0 6px; color: #9eb0aa; font-size: 10px; }
.review-box textarea { width: 100%; box-sizing: border-box; padding: 9px; resize: vertical; color: #e9efec; background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15); font: inherit; font-size: 11px; line-height: 1.5; }
.evidence-appendix { margin-top: 28px; padding: 27px; border: 1px solid var(--line); background: rgba(255,255,255,.72); }
.appendix-head { display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
.appendix-head .eyebrow { margin-bottom: 8px; }
.appendix-head h3 { margin: 0; font: 600 22px/1.2 Georgia, "Songti SC", serif; }
.appendix-head p:last-child { margin: 7px 0 0; color: #6d7a75; font-size: 11px; }
.appendix-head > span { color: var(--orange); font: 800 9px/1 "DM Sans", sans-serif; letter-spacing: .14em; }
.appendix-entry { min-width: 0; width: 100%; display: grid; grid-template-columns: 48px 215px minmax(0, 1fr) minmax(120px, 210px); gap: 14px; align-items: start; padding: 13px 10px; color: var(--ink); border: 0; border-top: 1px solid var(--line); background: transparent; text-align: left; cursor: pointer; }
.appendix-entry:hover, .appendix-entry.active { background: rgba(27,139,115,.07); }
.appendix-entry > b { color: var(--orange); font: 700 16px/1.4 "DM Sans", sans-serif; }
.appendix-locator code, .appendix-locator span, .appendix-locator small { display: block; }
.appendix-locator code { color: var(--mint); font-size: 10px; font-weight: 800; }
.appendix-locator span { margin-top: 4px; font-size: 10px; overflow-wrap: anywhere; }
.appendix-locator small { margin-top: 4px; color: #7a8782; font-size: 9px; }
.appendix-entry > p { min-width: 0; margin: 0; color: #596861; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; word-break: break-word; }
.appendix-linked { display: flex; flex-wrap: wrap; gap: 5px; }
.appendix-linked span { padding: 4px 5px; color: var(--forest); border: 1px solid rgba(23,77,64,.18); font-size: 8px; line-height: 1.3; overflow-wrap: anywhere; }
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
.evidence-row q { display: block; min-width: 0; color: #60706a; overflow-wrap: anywhere; word-break: break-word; white-space: normal; }
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
  .teacher-console-grid { grid-template-columns: 1fr; height: auto; }
  .report-preview-panel { height: 700px; border-right: 0; border-bottom: 1px solid var(--line); }
  .teacher-score-panel { max-height: none; overflow: visible; }
  .score-card-list { max-height: 620px; }
  .appendix-entry { grid-template-columns: 48px minmax(0, 1fr); }
  .appendix-entry > p, .appendix-linked { grid-column: 2; }
  .word-delivery-banner { align-items: flex-start; flex-direction: column; }
  .review-panel { position: static; }
  .diagnosis-panel { grid-template-columns: 1fr; }
}

@media (max-width: 600px) {
  .top-meta { display: none; }
  .topbar { padding-inline: 14px; }
  .top-actions { gap: 0; }
  .teacher-entry { padding: 8px 9px; }
  .hero, .workflow, .workbench, .result-section, footer { width: min(100% - 28px, 1180px); }
  .hero h1 { font-size: 42px; }
  .hero-actions, .workbench-head, .result-header, .profile, footer { align-items: flex-start; flex-direction: column; }
  .step-rail { grid-template-columns: 1fr; }
  .upload-panel { grid-template-columns: 1fr; }
  .rubric-panel { grid-template-columns: 1fr; }
  .data-notice { flex-direction: column; }
  .profile { gap: 14px; }
  .delivery-facts { flex-wrap: wrap; }
  .console-header, .report-toolbar, .appendix-head { align-items: flex-start; flex-direction: column; }
  .console-status { width: 100%; justify-content: space-between; }
  .report-preview-panel { height: 590px; }
  .score-panel-head { grid-template-columns: 1.2fr .8fr .8fr; }
  .score-panel-head > div { padding: 12px 9px; }
  .score-card-list { max-height: 560px; }
  .evidence-appendix { padding: 20px 14px; }
  .appendix-entry { grid-template-columns: 38px minmax(0, 1fr); gap: 9px; padding-inline: 4px; }
  .profile b, .profile span { text-align: left; }
  .evidence-row { grid-template-columns: 1fr; }
}
</style>
