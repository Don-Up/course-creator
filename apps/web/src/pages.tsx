import { useEffect, useState } from "react";

import { api, Course, Health } from "./api";


const workflowSteps = [
  ["intake", "接收并校验课程意图"],
  ["mission", "形成可审阅的任务定义"],
  ["blueprint", "规划课程结构与学习路径"],
  ["batch_plan", "安排可控的生成批次"],
  ["generation", "生成候选课程内容"],
  ["quality", "形成质量证据与修复结论"],
  ["release", "由人做出发布决定"],
];


export function CoursesPage() {
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
      </section>

      {error && <p className="notice error">{error}</p>}
      {!error && !health && <p className="notice">正在读取本地课程目录。</p>}

      <section className="course-grid" aria-label="示例课程">
        {courses.map((course) => <CourseCard key={course.slug} course={course} />)}
      </section>
    </>
  );
}


function CourseCard({ course }: { course: Course }) {
  return (
    <article className="course-card">
      <div className="card-meta">
        <span>{course.status}</span>
        <span>{course.chapters} 章</span>
      </div>
      <h2>{course.title}</h2>
      <p>{course.description}</p>
      <a className="course-link" href={course.href}>
        浏览已发布课程
      </a>
    </article>
  );
}


export function WorkflowPage() {
  return (
    <section className="workflow-page">
      <p className="eyebrow">Product contract</p>
      <h1>七阶段课程生产工作流</h1>
      <p>这是待实现的产品蓝图，当前脚手架不执行工作流、不调用模型，也不保存运行记录。</p>
      <ol className="workflow-list">
        {workflowSteps.map(([id, description], index) => (
          <li key={id}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <strong>{id}</strong>
              <p>{description}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}


export function NewCoursePage() {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Stage 01</p>
      <h1>新建课程</h1>
      <p>课程输入表单与创建流程将在第 01 阶“七步 Happy Path V0”中由你实现。</p>
    </section>
  );
}
