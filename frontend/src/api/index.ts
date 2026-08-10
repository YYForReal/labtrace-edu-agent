import axios from 'axios'

const http = axios.create({ baseURL: '/', timeout: 60000 })

export interface LabTraceBootstrap {
  product: { name: string; tagline: string; track: string; promise: string }
  word_capabilities: {
    input: string
    analysis: string
    output: string
    generic_template: string
  }
  mode: {
    id: string
    label: string
    disclaimer: string
    provider: string
    model: string
    external_processing: boolean
    daily_remaining: number
  }
  data_policy: {
    accepted_formats: string[]
    max_upload_mb: number
    identity_redaction: string
    model_payload: string
    retention: string
    teacher_responsibility: string
  }
  rubric: {
    experiment_id: string
    experiment_name: string
    total_score: number
    criteria: Array<{
      id: string
      name: string
      max_score: number
      description: string
    }>
  }
  rubric_template_url: string
  assignment_template: {
    name: string
    description: string
    input_url: string
    filename: string
  }
  samples: Array<{
    id: string
    domain: string
    name: string
    provenance: string
    input_url: string
    filename: string
  }>
  agent_steps: Array<{ id: string; label: string; detail: string }>
}

export interface LabTraceEvidence {
  evidence_id: string
  kind: string
  source_file: string
  locator: string
  excerpt: string
  reliability: number
  verification: string
}

export interface LabTraceCriterion {
  criterion_id: string
  criterion_name: string
  max_score: number
  score: number
  reason: string
  evidence_ids: string[]
  confidence: number
}

export interface LabTraceTask {
  task_id: string
  status: string
  mode: string
  input_filename: string
  document_profile: Record<string, number | string>
  rubric: {
    experiment_id: string
    experiment_name: string
    total_score: number
    criterion_count: number
    source: 'built_in' | 'teacher_upload'
  }
  agent_run: {
    adapter: string
    provider: string
    model: string
    attempts?: number
    latency_ms?: number
    tokens?: { input: number; output: number }
    fallback: boolean
    fallback_code?: string
    structured_output_validated: boolean
    vision_mode?: string
    images_sent?: number
  }
  privacy: {
    policy: string
    detected_sensitive_items: number
    detected_by_kind: Record<string, number>
    recognized_identity_terms_redacted: number
    images_sent_to_text_model: boolean
    retention: string
  }
  word_workflow: {
    input_is_word: boolean
    images_detected: number
    images_analyzed: number
    native_comments: number
    image_comments: number
    evidence_references: number
    evidence_appendix_written: boolean
    teacher_feedback_written: boolean
    score_written: boolean
    editable_word_available: boolean
    delivery_mode: 'template_fields' | 'generic_appendix' | 'comments_only'
  }
  trace: {
    trace_id: string
    rubric_id: string
    submission_alias: string
    evidence: LabTraceEvidence[]
    criteria: LabTraceCriterion[]
    model_total_score: number
    needs_human_review: boolean
    review_reasons: string[]
    review: {
      status: string
      reviewer_role: string
      final_score: number | null
      note: string
    }
  }
  evidence_appendix: Array<{
    reference_number: number
    citation: string
    evidence_id: string
    kind: string
    kind_label: string
    locator: string
    location_label: string
    excerpt: string
    reliability: number
    verification: string
    linked_criteria: string[]
  }>
  word_comments: Array<{
    comment_id: string
    criterion_id: string
    criterion_name: string
    evidence_id: string
    evidence_ids: string[]
    reference_numbers: number[]
    location_label: string
    text: string
    evidence_kind: string
    status: 'pending_review' | 'teacher_confirmed'
  }>
  learning_feedback: {
    student_focus: Array<{
      criterion_id: string
      criterion_name: string
      score_rate: number
      next_action: string
    }>
    message: string
  }
  diagnosis?: {
    record_count: number
    class_average: number
    top_weaknesses: Array<{
      criterion_id: string
      criterion_name: string
      average_rate: number
      sample_size: number
      teacher_action: string
    }>
  }
  events: Array<{ stage: string; message: string }>
  delivery: {
    available: boolean
    reason?: string
    details?: {
      annotations_count: number
      image_annotations_count: number
      score_injected: boolean
      comment_injected: boolean
      generic_section_appended: boolean
      delivery_mode: string
    }
  }
}

const labTraceApiUrl = (path: string) =>
  `${import.meta.env.BASE_URL}labtrace-api/${path.replace(/^\/+/, '')}`

export const labTracePublicUrl = (path: string) =>
  new URL(
    path.replace(/^\/+/, ''),
    new URL(import.meta.env.BASE_URL, window.location.origin),
  ).toString()

export const getLabTraceBootstrap = () =>
  http.get<LabTraceBootstrap>(labTraceApiUrl('bootstrap'))

export const gradeLabTraceDemo = (
  file: File,
  rubric?: File | null,
  allowExternalImages = false,
) => {
  const form = new FormData()
  form.append('report', file)
  if (rubric) form.append('rubric', rubric)
  form.append('allow_external_images', String(allowExternalImages))
  return http.post<LabTraceTask>(labTraceApiUrl('grade'), form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180000,
  })
}

export const reviewLabTraceDemo = (
  taskId: string,
  criteria: Array<{ criterion_id: string; score: number; reason: string }>,
  note: string,
) =>
  http.post<LabTraceTask>(labTraceApiUrl('review'), {
    task_id: taskId,
    criteria,
    note,
  })

export const deleteLabTraceTask = (taskId: string) =>
  http.delete<{ task_id: string; status: string }>(labTraceApiUrl(`tasks/${taskId}`))

export const getLabTraceTask = (taskId: string) =>
  http.get<LabTraceTask>(labTraceApiUrl(`tasks/${encodeURIComponent(taskId)}`))

export const labTraceDownloadUrl = (taskId: string, kind: 'source' | 'report' | 'trace') =>
  labTraceApiUrl(`tasks/${encodeURIComponent(taskId)}/download?kind=${kind}`)
