export type Health = {
  status: "ok";
  service: string;
};

export type Course = {
  slug: string;
  title: string;
  description: string;
  chapters: number;
  duration: string;
  status: string;
};

export type CourseCreate = {
  title: string;
  slug: string;
  audience: string;
  goals: string;
  scope: string;
  source_policy: string;
  delivery: string;
  preferred_chapter_count: number;
  effective_char_min: number;
  token_budget_mtokens: number | null;
  provider: string;
  model: string;
};

export type CourseCreated = {
  course: Course;
  run_id: string;
  status: string;
};

export type ChapterSummary = {
  key: string;
  number: number;
  title: string;
  path: string;
};

/**
 * The list of the courses, the shape the API answers with.
 *
 * The name is the one of the schema of the backend, so the two sides
 * call the same thing by the same name.
 */
export type CourseList = {
  items: Course[];
};

/**
 * The list of the chapters of one course.
 *
 * The name is the one of the schema of the backend, so the two sides
 * call the same thing by the same name.
 */
export type ChapterList = {
  items: ChapterSummary[];
};

export type Chapter = {
  key: string;
  path: string;
  content: string;
  content_hash: string;
  updated_at: string;
  snapshot_path: string;
};

export type RunCommandRead = {
  id: string;
  kind: string;
  status: string;
  attempt_count: number;
  created_at: string;
  updated_at: string;
};

export type RunRead = {
  id: string;
  course_slug: string;
  mode: string;
  status: string;
  current_step: string;
  provider: string;
  model: string;
  interrupt_type: string | null;
  error_message: string | null;
  trace_id: string | null;
  created_at: string;
  updated_at: string;
  active_command: RunCommandRead | null;
};

export type RunEventRead = {
  seq: number;
  id: string;
  event_type: string;
  step: string;
  message: string;
  created_at: string;
};

export type RunArtifactRead = {
  id: string;
  step: string;
  node: string;
  title: string;
  source: string;
  presentation: Record<string, unknown>;
  created_at: string;
};

export type WorkflowStepRead = {
  id: string;
  title: string;
  description: string;
  user_input: string;
  model_output: string;
  status: string;
};

export type RunDetail = {
  run: RunRead;
  events: RunEventRead[];
  artifacts: RunArtifactRead[];
  workflow_steps: WorkflowStepRead[];
};

export type RunSummary = {
  id: string;
  course_slug: string;
  mode: string;
  status: string;
  current_step: string;
  created_at: string;
  updated_at: string;
};

/**
 * The list of the runs, the shape the API answers with.
 *
 * The name is the one of the schema of the backend, so the two sides
 * call the same thing by the same name.
 */
export type RunList = {
  items: RunSummary[];
};

/**
 * One node of the workflow topology.
 *
 * A node is one unit of work of the workflow.  The stage says which
 * phase it belongs to, and the position says where it sits in the graph.
 */
export type WorkflowNode = {
  id: string;
  stage: string;
  title: string;
  description: string;
  position: number;
};

/**
 * One transition between two nodes of the workflow topology.
 */
export type WorkflowEdge = {
  source: string;
  target: string;
};

/**
 * One phase of the workflow topology.
 *
 * The nodes are the ids of the units of work that belong to the phase.
 */
export type WorkflowPhase = {
  id: string;
  title: string;
  description: string;
  user_input: string;
  model_output: string;
  nodes: string[];
};

/**
 * The topology of the workflow, the shape the API answers with.
 *
 * It is a projection of the graph of the workflow in the backend, so the
 * browser never writes the topology down itself.
 */
export type WorkflowSnapshot = {
  version: number;
  id: string;
  name: string;
  phases: WorkflowPhase[];
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

/**
 * The error a failed API answer turns into.
 *
 * The status code and the raw detail are kept, so the caller can tell a
 * taken slug (409) from a form the server cannot use (422).
 *
 * @param status The HTTP status code of the failed answer, for example 422.
 * @param detail The `detail` field of the answer, for example
 *   `[{ "loc": ["body", "slug"], "msg": "String should match pattern ..." }]`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(describeFailure(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Turn a failed answer into one line a person can read.
 *
 * @param status The HTTP status code of the failed answer, for example 409.
 * @param detail The `detail` field of the answer, for example
 *   "课程 slug 已存在".
 * @returns The message the user sees, for example
 *   "请求失败：409 · 课程 slug 已存在".
 */
function describeFailure(status: number, detail: unknown): string {
  if (typeof detail === "string" && detail.length > 0) {
    return `请求失败：${status} · ${detail}`;
  }
  if (Array.isArray(detail)) {
    return `请求失败：${status} · 表单有 ${detail.length} 处不合法`;
  }
  return `请求失败：${status}`;
}

/**
 * Send one request to the API and read the answer.
 *
 * @param path The path of the API, for example "/api/courses".
 * @param init The fetch options, for example
 *   `{ method: "POST", body: JSON.stringify(input) }`.
 * @returns The parsed answer, for example `{ items: [...] }`.
 * @throws ApiError when the API answers with a status code outside 2xx.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  let data: unknown = null;
  if (text.length > 0) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? (data as { detail: unknown }).detail
        : data;
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

/**
 * The API calls the frontend makes.
 */
export const api = {
  health: () => request<Health>("/api/health"),
  courses: () => request<CourseList>("/api/courses"),
  course: (slug: string) => request<Course>(`/api/courses/${encodeURIComponent(slug)}`),
  createCourse: (input: CourseCreate) =>
    request<CourseCreated>("/api/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  chapters: (slug: string) =>
    request<ChapterList>(
      `/api/courses/${encodeURIComponent(slug)}/chapters`,
    ),
  chapter: (slug: string, key: string) =>
    request<Chapter>(
      `/api/courses/${encodeURIComponent(slug)}/chapters/${encodeURIComponent(key)}`,
    ),
  runs: () => request<RunList>("/api/runs"),
  run: (runId: string) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`),
  workflow: () => request<WorkflowSnapshot>("/api/workflow"),
};
