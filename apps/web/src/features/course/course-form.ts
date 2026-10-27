import { CourseCreate } from "../../api";

export type StepNumber = 1 | 2 | 3;

export type CourseField = {
  name: keyof CourseCreate;
  label: string;
  kind: "text" | "textarea";
  step: StepNumber;
  hint: string;
  required: boolean;
  minLength?: number;
  maxLength?: number;
  min?: number;
  max?: number;
  defaultValue: string;
};

export type CourseStep = {
  number: StepNumber;
  title: string;
  description: string;
};

export type FieldProblems = Record<string, string>;

export type FieldProblem = {
  field: string;
  message: string;
  step: StepNumber;
};

export const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export const COURSE_STEPS: CourseStep[] = [
  { number: 1, title: "课程身份", description: "这门课叫什么、给谁学" },
  { number: 2, title: "学习任务", description: "学完要能做什么、覆盖到哪" },
  { number: 3, title: "生成约束", description: "章节数、字数与模型参数" },
];

export const COURSE_FIELDS: CourseField[] = [
  {
    name: "title",
    label: "课程标题",
    kind: "text",
    step: 1,
    hint: "2–120 个字符",
    required: true,
    minLength: 2,
    maxLength: 120,
    defaultValue: "",
  },
  {
    name: "slug",
    label: "课程短名",
    kind: "text",
    step: 1,
    hint: "小写字母、数字与单个连字符，例如 python-101",
    required: true,
    defaultValue: "",
  },
  {
    name: "audience",
    label: "面向的学习者",
    kind: "textarea",
    step: 1,
    hint: "2–500 个字符",
    required: true,
    minLength: 2,
    maxLength: 500,
    defaultValue: "",
  },
  {
    name: "goals",
    label: "学习目标",
    kind: "textarea",
    step: 2,
    hint: "5–3000 个字符，写清楚学完能做成什么",
    required: true,
    minLength: 5,
    maxLength: 3000,
    defaultValue: "",
  },
  {
    name: "scope",
    label: "覆盖范围",
    kind: "textarea",
    step: 2,
    hint: "2–3000 个字符",
    required: true,
    minLength: 2,
    maxLength: 3000,
    defaultValue: "",
  },
  {
    name: "source_policy",
    label: "资料来源策略",
    kind: "text",
    step: 3,
    hint: "写进 course.json 的来源说明",
    required: false,
    defaultValue: "允许使用用户资料与公开官方资料",
  },
  {
    name: "delivery",
    label: "交付形态",
    kind: "text",
    step: 3,
    hint: "例如 Markdown + HTML",
    required: false,
    defaultValue: "Markdown + HTML",
  },
  {
    name: "preferred_chapter_count",
    label: "期望章节数",
    kind: "text",
    step: 3,
    hint: "1–60 的整数",
    required: false,
    min: 1,
    max: 60,
    defaultValue: "12",
  },
  {
    name: "effective_char_min",
    label: "单课最少有效字数",
    kind: "text",
    step: 3,
    hint: "1000–50000 的整数",
    required: false,
    min: 1000,
    max: 50000,
    defaultValue: "12000",
  },
  {
    name: "token_budget_mtokens",
    label: "Token 预算（百万）",
    kind: "text",
    step: 3,
    hint: "0.01–10000，留空表示不设预算",
    required: false,
    min: 0.01,
    max: 10000,
    defaultValue: "",
  },
  {
    name: "provider",
    label: "Provider",
    kind: "text",
    step: 3,
    hint: "默认 codex_gateway",
    required: false,
    defaultValue: "codex_gateway",
  },
  {
    name: "model",
    label: "模型",
    kind: "text",
    step: 3,
    hint: "默认 llm-gateway--kimi-k3",
    required: false,
    defaultValue: "llm-gateway--kimi-k3",
  },
];

/**
 * Build the starting values of the course form.
 *
 * Every field of the twelve gets its default, so the third step is already
 * filled in and only the first two steps ask the user for anything.
 *
 * @returns The value of every field, keyed by field name, for example
 *   `{ title: "", slug: "", delivery: "Markdown + HTML" }`.
 */
export function initialValues(): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of COURSE_FIELDS) {
    values[field.name] = field.defaultValue;
  }
  return values;
}

/**
 * List the fields that belong to one step of the wizard.
 *
 * @param step The number of the step, for example 2.
 * @returns The fields of that step, for example the `goals` and `scope` fields.
 */
export function fieldsOfStep(step: StepNumber): CourseField[] {
  return COURSE_FIELDS.filter((field) => field.step === step);
}

/**
 * Find the step a field belongs to.
 *
 * @param name The name of the field, for example "slug".
 * @returns The number of the step, for example 1. An unknown name falls back
 *   to the first step.
 */
export function stepOfField(name: string): StepNumber {
  const field = COURSE_FIELDS.find((candidate) => candidate.name === name);
  return field ? field.step : 1;
}

/**
 * Check one field of the form against the rule the API will check it with.
 *
 * The rules are the same as the ones in the backend schema, so the form
 * catches a bad value before the request is sent. The backend stays the
 * authority; this only saves the user a round trip.
 *
 * @param field The field to check, for example the `slug` field.
 * @param raw The text the user typed, for example "Python 101".
 * @returns The message to show under the field, for example
 *   "只能用小写字母、数字与单个连字符", or null when the value is fine.
 */
export function validateField(field: CourseField, raw: string): string | null {
  const value = raw.trim();
  if (field.required && value.length === 0) {
    return "这一项不能为空";
  }
  if (value.length === 0) {
    return null;
  }
  if (field.minLength !== undefined && value.length < field.minLength) {
    return `至少 ${field.minLength} 个字符`;
  }
  if (field.maxLength !== undefined && value.length > field.maxLength) {
    return `最多 ${field.maxLength} 个字符`;
  }
  if (field.name === "slug" && !SLUG_PATTERN.test(value)) {
    return "只能用小写字母、数字与单个连字符";
  }
  if (field.min !== undefined || field.max !== undefined) {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) {
      return "这一项要填一个数字";
    }
    if (field.min !== undefined && parsed < field.min) {
      return `不能小于 ${field.min}`;
    }
    if (field.max !== undefined && parsed > field.max) {
      return `不能大于 ${field.max}`;
    }
  }
  return null;
}

/**
 * Check every field of one step.
 *
 * @param step The number of the step, for example 1.
 * @param values The value of every field, for example `{ title: "Python 入门" }`.
 * @returns The message of every field that is wrong, keyed by field name.
 *   An empty object means the step is fine.
 */
export function validateStep(step: StepNumber, values: Record<string, string>): FieldProblems {
  const problems: FieldProblems = {};
  for (const field of fieldsOfStep(step)) {
    const message = validateField(field, values[field.name] ?? "");
    if (message) {
      problems[field.name] = message;
    }
  }
  return problems;
}

/**
 * Check every field of the whole form.
 *
 * @param values The value of every field, for example `{ title: "Python 入门" }`.
 * @returns The message of every field that is wrong, keyed by field name.
 *   An empty object means the form is fine.
 */
export function validateAll(values: Record<string, string>): FieldProblems {
  const problems: FieldProblems = {};
  for (const field of COURSE_FIELDS) {
    const message = validateField(field, values[field.name] ?? "");
    if (message) {
      problems[field.name] = message;
    }
  }
  return problems;
}

/**
 * Turn the form values into the body the API expects.
 *
 * Text is trimmed, the three numbers are turned into numbers, and an empty
 * token budget becomes null instead of zero.
 *
 * @param values The value of every field, for example
 *   `{ title: " Python 入门 ", slug: "python-101" }`.
 * @returns The body of the create request, for example
 *   `{ title: "Python 入门", slug: "python-101", token_budget_mtokens: null }`.
 */
export function toPayload(values: Record<string, string>): CourseCreate {
  const budget = values.token_budget_mtokens?.trim() ?? "";
  return {
    title: values.title?.trim() ?? "",
    slug: values.slug?.trim() ?? "",
    audience: values.audience?.trim() ?? "",
    goals: values.goals?.trim() ?? "",
    scope: values.scope?.trim() ?? "",
    source_policy: values.source_policy?.trim() ?? "",
    delivery: values.delivery?.trim() ?? "",
    preferred_chapter_count: Number(values.preferred_chapter_count),
    effective_char_min: Number(values.effective_char_min),
    token_budget_mtokens: budget.length > 0 ? Number(budget) : null,
    provider: values.provider?.trim() ?? "",
    model: values.model?.trim() ?? "",
  };
}

/**
 * Guess the short name of a course from its title.
 *
 * Everything that is not a lowercase letter or a digit becomes one hyphen,
 * and a hyphen at either end is dropped.
 *
 * @param title The title of the course, for example "Python 101 入门".
 * @returns The guessed short name, for example "python-101". A title without
 *   any letter or digit gives an empty string.
 */
export function slugFromTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Read the field errors the API sends back.
 *
 * The API answers a bad request with a list of `loc` and `msg` pairs; this
 * turns that list into one entry per field and works out which step of the
 * wizard the field lives in.
 *
 * @param detail The `detail` field of a 422 answer, for example
 *   `[{ "loc": ["body", "slug"], "msg": "String should match pattern ..." }]`.
 * @returns One entry per field, for example
 *   `[{ field: "slug", message: "String should match pattern ...", step: 1 }]`.
 *   A detail that is not a list gives an empty array.
 */
export function collectFieldProblems(detail: unknown): FieldProblem[] {
  if (!Array.isArray(detail)) {
    return [];
  }
  const problems: FieldProblem[] = [];
  for (const item of detail) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const record = item as { loc?: unknown; msg?: unknown };
    const location = Array.isArray(record.loc)
      ? record.loc.filter((part) => part !== "body").map((part) => String(part)).join(".")
      : "";
    if (location.length === 0) {
      continue;
    }
    const message = typeof record.msg === "string" ? record.msg : "这一项不合法";
    problems.push({ field: location, message, step: stepOfField(location) });
  }
  return problems;
}
