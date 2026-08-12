export type CourseLesson = {
  number: number;
  code?: string;
  title: string;
  summary?: string;
  status: string;
  markdown: string;
  href?: string;
};

export type CourseQualitySnapshot = {
  revision: string | null;
  course_integration: {
    passed?: boolean;
    build?: Record<string, unknown>;
    validation?: Record<string, unknown>;
    label?: string;
  };
  source_contract_gate: { passed?: boolean; diagnostics?: Array<Record<string, unknown>>; revision?: string };
  build_gate: { passed?: boolean; revision?: string };
  artifact_gate: { passed?: boolean | null; revision?: string };
  quality_cycle: {
    cycle_id?: string;
    iteration?: number;
    initial_issue_count?: number;
    new_issue_count?: number;
    closed_count?: number;
    queue_size?: number;
    current_chapter?: number;
    escalation_level?: string;
    converged?: boolean;
  };
  chapters: Array<{
    chapter: number;
    path: string;
    effective_chars?: number;
    effective_char_min?: number;
    humanizer_score?: number;
    semantic_decision?: string;
    chapter_passed: boolean;
    batch_id?: string;
    batch_integration_passed?: boolean | null;
    course_integration_passed?: boolean | null;
    repair_status?: string;
    updated_at?: string;
  }>;
};

export type Course = {
  slug: string;
  title: string;
  description: string;
  status: string;
  duration: string;
  chapter_count: number;
  quality_report_count: number;
  has_workspace: boolean;
  has_course_json: boolean;
  lessons: CourseLesson[];
  course_quality_snapshot?: CourseQualitySnapshot;
  runs?: RunSummary[];
  resumable_run_id?: string | null;
  resumable_run_step?: string | null;
};

export type Chapter = {
  key: string;
  number: number;
  code?: string;
  title: string;
  summary: string;
  path: string;
  content: string;
  content_hash: string;
  updated_at: string;
  snapshot_path?: string;
};

export type WorkflowStep = {
  id: string;
  title: string;
  description: string;
  user_input: string;
  model_output: string;
  status: "completed" | "active" | "pending";
  artifacts: RunArtifact[];
};

export type WorkspaceFileSummary = {
  path: string;
  size: number;
  editable: boolean;
  updated_at: string;
};

export type WorkspaceFile = WorkspaceFileSummary & {
  content: string;
  content_hash: string;
  snapshot_path?: string;
};

export type RunArtifact = {
  id: string;
  step: string;
  node: string;
  title: string;
  source: "model" | "recovered" | string;
  presentation: {
    headline: string;
    conclusion: string;
    highlights: string[];
    metrics: Record<string, string | number | boolean>;
    blockers?: string[];
    issues: string[];
    next_action: string;
  };
  raw_output: unknown;
  created_at: string;
};

export type RunEvent = {
  seq: number;
  id: string;
  event_type: string;
  step: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type BudgetSnapshot = {
  effective_policy: Record<string, number | null>;
  usage_totals: { input_tokens: number; output_tokens: number; total_tokens: number; model_calls: number; estimated_cost_microusd: number | null };
  remaining: Record<string, number | null>;
  status: "WITHIN_LIMIT" | "EXCEEDED";
  violations: Array<{ metric: string; limit: number; actual: number }>;
  top_consumers: Array<{ provider?: string; model?: string; stage?: string; total_tokens?: number | null; duration_ms?: number | null }>;
  latest_adjustments: Array<{ reason: string; created_at: string }>;
};

export type TraceSpan = {
  id: string; parent_span_id?: string | null; kind: string; name: string; status: string;
  stage?: string | null; duration_ms?: number | null; error_message?: string | null;
};
export type TraceProjection = { trace_id: string; run_id: string; spans: TraceSpan[] };

export type RunSummary = {
  id: string;
  course_slug: string;
  mode: string;
  status: string;
  current_step: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
  request?: Record<string, unknown>;
};

export type RunDetail = RunSummary & {
  request: Record<string, unknown>;
  interrupt_type?: string;
  interrupt_payload?: {
    type: string;
    step: string;
    title: string;
    output: unknown;
    actions: Array<"APPROVE" | "REVISE" | "STOP">;
  };
  error_message?: string;
  legacy_current_step?: string;
  quality_repair_in_progress?: boolean;
  events: RunEvent[];
  workflow_steps: WorkflowStep[];
  artifacts: RunArtifact[];
  repair_tasks?: Array<{
    id: string;
    batch_id?: string | null;
    chapter?: number | null;
    severity: "blocker" | "major" | "minor" | string;
    category: string;
    status: string;
    issue: string;
    attempt_count: number;
    evidence?: { quoted_source?: string };
    verification?: { outcome?: string; reason?: string } | null;
  }>;
  repair_task_summary?: { open: number; verified: number; needs_human: number };
  course_quality_snapshot?: CourseQualitySnapshot;
  quality_cycle?: CourseQualitySnapshot["quality_cycle"];
  revision?: string;
  active_command?: CommandExecution | null;
  command_timeline?: CommandExecution[];
  current_node_execution?: NodeExecution | null;
  node_execution_timeline?: NodeExecution[];
};

export type CommandExecution = {
  id: string;
  kind: "START" | "RESUME" | "CONTINUE" | "STOP" | string;
  status: string;
  attempt_count: number;
  max_attempts: number;
  leased_by?: string | null;
  lease_expires_at?: string | null;
  heartbeat_at?: string | null;
  cancel_requested: boolean | number;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
};

export type NodeExecution = {
  id: string;
  command_id?: string | null;
  node_id: string;
  status: string;
  attempt_count: number;
  leased_by?: string | null;
  heartbeat_at?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export type WorkflowNode = {
  id: string; phase: string; title: string; handler: string;
  execution_mode?: "llm" | "hybrid" | "deterministic" | "approval" | "system";
  agents: string[]; tools: string[];
};
export type WorkflowEdge = { from: string; to: string; label: string };
export type WorkflowTopology = { mode: string; title: string; steps: WorkflowStep[]; phases: Array<[string, string, string]>; nodes: WorkflowNode[]; edges: WorkflowEdge[] };
export type WorkflowSnapshot = { version: string; default_mode: string; topologies: WorkflowTopology[]; agents: Array<{ id: string; version: string; role: string; model_policy: string; tools: string[] }>; tools: Array<{ id: string; callers: string[]; idempotent: boolean }> };

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
};

export const api = {
  workflow: () => request<WorkflowSnapshot>("/api/workflow"),
  health: () =>
    request<{
      status: string;
      provider: string;
      model: string;
      provider_configured: boolean;
      deepseek_configured: boolean;
      codex_gateway_available: boolean;
      codex_gateway_models: string[];
      reasoning_effort: string;
      service_tier: string;
      mode: string;
    }>("/api/health"),
  updateProviderPreferences: (payload: {
    provider: "codex_gateway" | "deepseek";
    model: string;
    deepseek_api_key: string;
    llm_base_url: string;
  }) =>
    request<{ provider: string; model: string; provider_configured: boolean }>(
      "/api/settings/provider",
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  courses: () => request<{ items: Course[] }>("/api/courses"),
  course: (slug: string) => request<Course>(`/api/courses/${slug}`),
  chapter: (slug: string, key: string) =>
    request<Chapter>(
      `/api/courses/${slug}/chapters/${encodeURIComponent(key)}`,
    ),
  saveChapter: (
    slug: string,
    key: string,
    payload: {
      content: string;
      expected_hash: string;
      reason: string;
      rebuild: boolean;
    },
  ) =>
    request<{ chapter: Chapter; build?: ToolResult }>(
      `/api/courses/${slug}/chapters/${encodeURIComponent(key)}`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  createCourse: (payload: Record<string, unknown>) =>
    request<{ course: Course; run_id: string; command_id: string; duplicate: boolean }>("/api/courses", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  startRun: (
    slug: string,
    payload: {
      provider: string;
      model: string;
      scope: string;
      chapter_keys: string[];
      instruction: string;
    },
  ) =>
    request<{ run_id: string; command_id: string; duplicate: boolean }>(`/api/courses/${slug}/runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  run: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  budget: (id: string) => request<BudgetSnapshot>(`/api/runs/${id}/budget`),
  trace: (id: string) => request<TraceProjection>(`/api/runs/${id}/trace`),
  resolveRun: (
    id: string,
    action: "APPROVE" | "REVISE" | "STOP",
    feedback: string,
  ) =>
    request<{ run_id: string; status: string; command_id: string; duplicate: boolean }>(`/api/runs/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ action, feedback }),
    }),
  continueRun: async (id: string, feedback = "", runStatus?: string) => {
    try {
      return await request<{ run_id: string; status: string; command_id: string; duplicate: boolean }>(`/api/runs/${id}/continue`, {
        method: "POST",
        body: JSON.stringify({ feedback }),
      });
    } catch (error) {
      // A UI update can be served by Vite before a locally running older API
      // process has been restarted. That process lacks /continue, but its
      // legacy endpoint can only resume an approval checkpoint. A failed run
      // must retain its LangGraph checkpoint and never be sent to /resolve.
      if (
        error instanceof Error &&
        error.message === "Not Found" &&
        runStatus === "WAITING_APPROVAL"
      ) {
        return api.resolveRun(id, "REVISE", feedback);
      }
      if (error instanceof Error && error.message === "Not Found") {
        throw new Error(
          "本地 Agent 后端版本过旧，无法从失败检查点继续。请完全重启本地后端服务后再试。",
        );
      }
      throw error;
    }
  },
  stopRun: (id: string) => request<{ run_id: string; status: string; command_id: string; duplicate: boolean }>(`/api/runs/${id}/stop`, { method: "POST" }),
  runTool: (slug: string, action: "build" | "validate") =>
    request<ToolResult>(`/api/courses/${slug}/tools/${action}`, {
      method: "POST",
    }),
  workspaceFiles: (slug: string) =>
    request<{ items: WorkspaceFileSummary[] }>(
      `/api/courses/${slug}/workspace`,
    ),
  workspaceFile: (slug: string, path: string) =>
    request<WorkspaceFile>(
      `/api/courses/${slug}/workspace/file?path=${encodeURIComponent(path)}`,
    ),
  saveWorkspaceFile: (
    slug: string,
    path: string,
    content: string,
    expectedHash: string,
  ) =>
    request<WorkspaceFile>(
      `/api/courses/${slug}/workspace/file?path=${encodeURIComponent(path)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content, expected_hash: expectedHash }),
      },
    ),
  uploadWorkspaceResource: (
    slug: string,
    payload: { filename: string; content_base64: string; media_type: string },
  ) =>
    request<{ path: string; size: number }>(
      `/api/courses/${slug}/workspace/resources`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  appendWorkspaceResourceNote: (slug: string, content: string) =>
    request<WorkspaceFile>(`/api/courses/${slug}/workspace/resources/note`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};

export type ToolResult = {
  action: string;
  command: string[];
  exit_code: number | null;
  stdout: string;
  stderr: string;
  succeeded: boolean;
};
