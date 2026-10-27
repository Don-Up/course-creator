import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError, Course, Health } from "../api";
import {
  COURSE_STEPS,
  FieldProblem,
  FieldProblems,
  StepNumber,
  collectFieldProblems,
  fieldsOfStep,
  initialValues,
  slugFromTitle,
  toPayload,
  validateAll,
  validateStep,
} from "../features/course/course-form";


/**
 * The landing page: the health of the API and the list of local courses.
 *
 * @returns The page with the API status, the "新建课程" entry and one card
 *   per course.
 */
export function Dashboard() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([api.health(), api.courses()])
      .then(([healthResponse, coursesResponse]) => {
        setHealth(healthResponse);
        setCourses(coursesResponse.items);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "无法读取课程信息");
      });
  }, []);

  return (
    <>
      <section className="page-intro">
        <p className="eyebrow">Training scaffold</p>
        <h1>从这里开始搭建课程生成 Agent</h1>
        <p>React 与 FastAPI 已连通。课程生产能力将在实施指引的后续阶段逐步完成。</p>
        <p className={health ? "api-status ok" : "api-status"}>
          API {health ? "已连接" : "连接中"}
        </p>
        <p className="intro-actions">
          <Link className="primary-action" to="/new">新建课程</Link>
        </p>
      </section>

      {error && <p className="notice error">{error}</p>}
      {!error && !health && <p className="notice">正在读取本地课程目录。</p>}

      <section className="course-grid" aria-label="课程列表">
        {courses.map((course) => <CourseCard key={course.slug} course={course} />)}
      </section>
    </>
  );
}


/**
 * One course in the list of the dashboard.
 *
 * @param course The course to show, for example the course with the slug
 *   "python-101".
 * @returns The card, with a link to the course page of that course.
 */
function CourseCard({ course }: { course: Course }) {
  return (
    <article className="course-card">
      <div className="card-meta">
        <span>{course.status}</span>
        <span>{course.chapters} 章</span>
      </div>
      <h2>{course.title}</h2>
      <p>{course.description}</p>
      <Link className="course-link" to={`/courses/${course.slug}`}>查看课程 →</Link>
    </article>
  );
}


/**
 * The three step wizard that creates a course.
 *
 * The form holds the values of the twelve fields, the step it is on, and the
 * messages of the fields that are wrong. Each step is checked before the
 * wizard moves on, and the whole form is checked again before the request
 * goes out.
 *
 * @returns The wizard, with the three steps, the fields of the current step
 *   and the buttons of the current step.
 */
export function NewCourse() {
  const navigate = useNavigate();
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [step, setStep] = useState<StepNumber>(1);
  const [visited, setVisited] = useState<StepNumber[]>([1]);
  const [problems, setProblems] = useState<FieldProblems>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitProblems, setSubmitProblems] = useState<FieldProblem[]>([]);
  const [submitting, setSubmitting] = useState(false);

  /**
   * Take the new text of one field.
   *
   * The message of the field is dropped as well, because the value the user
   * just typed has not been checked yet.
   *
   * @param name The name of the field, for example "title".
   * @param value The text the user typed, for example "Python 入门".
   * @returns Nothing; the new value is kept in the state of the form.
   */
  function update(name: string, value: string) {
    setValues((current) => ({ ...current, [name]: value }));
    setProblems((current) => {
      if (!current[name]) {
        return current;
      }
      const next = { ...current };
      delete next[name];
      return next;
    });
  }

  /**
   * Go back to a step the user has already reached.
   *
   * A step that was never reached stays locked, so the wizard cannot skip a
   * step that was never filled in.
   *
   * @param target The number of the step to show, for example 1.
   * @returns Nothing; the step of the wizard is changed when the step was
   *   reached before.
   */
  function goToStep(target: StepNumber) {
    if (!visited.includes(target)) {
      return;
    }
    setStep(target);
  }

  /**
   * Check the current step and move one step further.
   *
   * @returns Nothing; when the step is wrong the wizard stays where it is
   *   and shows the message of every field that is wrong.
   */
  function goNext() {
    const found = validateStep(step, values);
    setProblems(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    const next = (step + 1) as StepNumber;
    setStep(next);
    setVisited((current) => (current.includes(next) ? current : [...current, next]));
  }

  /**
   * Go one step back.
   *
   * @returns Nothing; the step of the wizard is one lower.
   */
  function goBack() {
    setStep((step - 1) as StepNumber);
  }

  /**
   * Fill the short name from the title.
   *
   * A title without any letter or digit has no short name to guess, so the
   * field gets a message instead of a value.
   *
   * @returns Nothing; the short name field holds the guessed name.
   */
  function fillSlugFromTitle() {
    const slug = slugFromTitle(values.title ?? "");
    if (slug.length === 0) {
      setProblems((current) => ({
        ...current,
        slug: "标题里没有能用的字母或数字，请自己写一个短名",
      }));
      return;
    }
    update("slug", slug);
  }

  /**
   * Send the form to the API and create the course.
   *
   * The whole form is checked first; when a field is wrong the wizard jumps
   * to the first step that holds one. When the API refuses the form, the
   * message of the API is shown with one button per field, so the user can
   * jump back to the step that holds the field.
   *
   * @returns Nothing; on success the browser goes to the page of the new
   *   course, on failure the error is shown above the form.
   */
  async function submit() {
    const found = validateAll(values);
    setProblems(found);
    if (Object.keys(found).length > 0) {
      const broken = COURSE_STEPS.find((courseStep) =>
        fieldsOfStep(courseStep.number).some((field) => found[field.name]),
      );
      if (broken) {
        setStep(broken.number);
        setVisited((current) =>
          current.includes(broken.number) ? current : [...current, broken.number],
        );
      }
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    setSubmitProblems([]);
    try {
      const created = await api.createCourse(toPayload(values));
      navigate(`/courses/${created.course.slug}`);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setSubmitError(reason.message);
        setSubmitProblems(collectFieldProblems(reason.detail));
      } else {
        setSubmitError("建课失败：请求没有送达后端，请确认 API 在运行");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const conflict = submitError !== null && submitError.includes("409");

  return (
    <section className="course-wizard">
      <p className="eyebrow">Stage 01</p>
      <h1>新建课程</h1>
      <p className="wizard-lead">
        三段表单：课程身份、学习任务、生成约束。填完最后一段就建课，
        课程当场落到本地课程目录里。
      </p>

      {submitError && (
        <div className="notice error">
          <p>{submitError}</p>
          {conflict && (
            <p className="field-hint">
              这个短名已经被占用了。换个短名再提交，原来那门课一个字节都不会被改动。
            </p>
          )}
          {submitProblems.length > 0 && (
            <ul className="error-list">
              {submitProblems.map((problem) => (
                <li key={`${problem.field}-${problem.message}`}>
                  <button type="button" onClick={() => goToStep(problem.step)}>
                    {problem.field}：{problem.message}（回到第 {problem.step} 段）
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <ol className="wizard-steps">
        {COURSE_STEPS.map((courseStep) => {
          const state =
            courseStep.number === step
              ? "active"
              : visited.includes(courseStep.number)
                ? "done"
                : "pending";
          return (
            <li key={courseStep.number} className={state}>
              <button
                type="button"
                disabled={!visited.includes(courseStep.number)}
                onClick={() => goToStep(courseStep.number)}
              >
                <span className="step-number">{String(courseStep.number).padStart(2, "0")}</span>
                <span className="step-title">{courseStep.title}</span>
                <span className="step-description">{courseStep.description}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <form
        className="wizard-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="wizard-panel">
          {fieldsOfStep(step).map((field) => (
            <div className="form-field" key={field.name}>
              <label htmlFor={`field-${field.name}`}>
                {field.label}
                {field.required && <span className="required-mark">必填</span>}
              </label>
              {field.kind === "textarea" ? (
                <textarea
                  id={`field-${field.name}`}
                  rows={3}
                  value={values[field.name] ?? ""}
                  onChange={(event) => update(field.name, event.target.value)}
                />
              ) : (
                <input
                  id={`field-${field.name}`}
                  type="text"
                  value={values[field.name] ?? ""}
                  onChange={(event) => update(field.name, event.target.value)}
                />
              )}
              <div className="field-foot">
                <span className="field-hint">{field.hint}</span>
                {field.name === "slug" && (
                  <button type="button" className="link-button" onClick={fillSlugFromTitle}>
                    从标题生成
                  </button>
                )}
              </div>
              {problems[field.name] && <p className="field-error">{problems[field.name]}</p>}
            </div>
          ))}
        </div>

        <div className="wizard-actions">
          {step > 1 && (
            <button type="button" className="ghost-button" onClick={goBack}>上一步</button>
          )}
          {step < 3 && (
            <button type="button" className="primary-button" onClick={goNext}>下一步</button>
          )}
          {step === 3 && (
            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? "建课中…" : "提交建课"}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}


/**
 * The page of one course, read from the slug in the address.
 *
 * The page shows what the course skeleton already holds. The generation
 * itself is not part of this phase, so the page says so instead of showing
 * a progress that does not exist.
 *
 * @returns The page of the course, for example the page of "python-101".
 */
export function CourseWorkspace() {
  const { slug = "" } = useParams();
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api
      .course(slug)
      .then(setCourse)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "无法读取这门课");
      });
  }, [slug]);

  return (
    <section className="course-workspace">
      <p className="eyebrow">Course</p>
      {error && <p className="notice error">{error}</p>}
      {!error && !course && <p className="notice">正在读取这门课。</p>}
      {course && (
        <>
          <h1>{course.title}</h1>
          <p className="workspace-slug">{course.slug}</p>
          <dl className="workspace-facts">
            <div>
              <dt>状态</dt>
              <dd>{course.status}</dd>
            </div>
            <div>
              <dt>章节数</dt>
              <dd>{course.chapters}</dd>
            </div>
            <div>
              <dt>时长</dt>
              <dd>{course.duration || "待蓝图确认"}</dd>
            </div>
          </dl>
          <p>{course.description}</p>
          <p className="notice">
            课程骨架已经落盘，但生成流程还没有实现：那属于阶段 P2 起的后续计划。
          </p>
          <p className="intro-actions">
            <Link className="primary-action" to="/">回到课程列表</Link>
          </p>
        </>
      )}
    </section>
  );
}
