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
 * The four API calls the frontend makes.
 */
export const api = {
  health: () => request<Health>("/api/health"),
  courses: () => request<{ items: Course[] }>("/api/courses"),
  course: (slug: string) => request<Course>(`/api/courses/${encodeURIComponent(slug)}`),
  createCourse: (input: CourseCreate) =>
    request<CourseCreated>("/api/courses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
};
