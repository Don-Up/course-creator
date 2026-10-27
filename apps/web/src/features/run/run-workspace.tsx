import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";

import { api, RunEventRead, WorkflowStepRead } from "../../api";
import { LiveAgentActivity } from "./activity";
import { authoritativeEffectiveChars, effectiveCharCount } from "./quality-metrics";
import { shouldPollRun } from "./run-polling";
import "./run.css";

/**
 * The workbench of one run.
 *
 * A run is the record of one attempt at a course.  This page answers
 * three questions about it, and all three come out of the read model of
 * the API:
 *
 * - **Where is the run?**  The seven stages are drawn as a bar, and the
 *   one the run is at is the one that is highlighted.
 * - **What happened?**  The events of the run are drawn as a track,
 *   newest first, and the stage that is running has its own live view.
 * - **What does it look like?**  The chapters of the course can be read
 *   here, without leaving the page.
 *
 * The page keeps itself up to date by asking the API again, and it stops
 * asking when the answer can no longer change: that decision is the one
 * of `shouldPollRun`, and it is the one rule this page borrows.
 */

/**
 * The number of the quality snapshot of a chapter.
 *
 * The snapshot is the current fact about the quality of a course, and it
 * is the number the workbench shows.  It is read from
 * `quality/course-quality-snapshot.json`, and the endpoint that reads it
 * arrives with the quality snapshot of a later phase.  Until then there
 * is no snapshot to be had, and the number falls back to the text of the
 * chapter.  The rule is already the one of the contract: when the
 * snapshot arrives it wins, and nothing here has to change.
 */
const SNAPSHOT_CHARS: number | undefined = undefined;

/**
 * Say in one word where a stage stands.
 *
 * @param step The stage the label is about, for example the "mission".
 * @param currentStep The stage the run is at, for example "intake".
 * @returns The label of the stage, for example "当前阶段".
 */
function stageStateLabel(step: WorkflowStepRead, currentStep: string): string {
  if (step.status === "completed") {
    return "已完成";
  }
  if (step.id === currentStep) {
    return "当前阶段";
  }
  return "未开始";
}

/**
 * The seven stages of the workflow, as a bar.
 *
 * Every stage gets a colour that says where it stands: done, running or
 * not started yet.  A stage can be picked, and the page then shows what
 * that stage is about.
 *
 * @param steps The stages of the workflow, in the order of the contract.
 * @param currentStep The stage the run is at, for example "intake".
 * @param selectedStep The stage the person picked, for example "mission".
 * @param onSelect What to call when a stage is picked.
 * @returns The element with the bar of the seven stages.
 */
export function WorkflowMap({
  steps,
  currentStep,
  selectedStep,
  onSelect,
}: {
  steps: WorkflowStepRead[];
  currentStep: string;
  selectedStep: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="workflow-map" aria-label="课程生成的七个阶段">
      {steps.map((step, index) => (
        <button
          type="button"
          key={step.id}
          className={`workflow-node ${step.status}${
            selectedStep === step.id ? " selected" : ""
          }`}
          onClick={() => onSelect(step.id)}
          aria-current={currentStep === step.id ? "step" : undefined}
        >
          <span className="workflow-node-index">{index + 1}</span>
          <span className="workflow-node-title">{step.title}</span>
          <span className="workflow-node-state">
            {stageStateLabel(step, currentStep)}
          </span>
        </button>
      ))}
    </nav>
  );
}

/**
 * The events of the run, newest first.
 *
 * The order is the order in which they happened, turned around: the
 * person who opens the workbench wants to read the last thing that
 * happened first, and the track grows upwards.
 *
 * @param events The events of the run, in the order the API gives them.
 * @returns The element with the track of the events.
 */
export function EventTrack({ events }: { events: RunEventRead[] }) {
  const ordered = events.slice().sort((left, right) => right.seq - left.seq);
  return (
    <section className="event-track" aria-label="运行事件">
      <h2>发生了什么</h2>
      {ordered.length === 0 ? (
        <p className="event-track-empty">这条 Run 还没有留下事件。</p>
      ) : (
        <ol>
          {ordered.map((event) => (
            <li key={event.id}>
              <span className="event-type">{event.event_type}</span>
              <span className="event-step">{event.step}</span>
              <span className="event-message">{event.message}</span>
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleTimeString()}
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/**
 * The chapters of the course, read only.
 *
 * The chapters are read through the chapter API of the course, so what
 * is shown here is the text that is on the disk.  Nothing can be changed
 * here: the workbench shows what the run produced, and the editor of a
 * course is a different page.
 *
 * @param slug The slug of the course, for example "python-101".
 * @returns The element with the chapter picker and the chapter itself.
 */
export function ChapterPreview({ slug }: { slug: string }) {
  const [picked, setPicked] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["chapters", slug],
    queryFn: () => api.chapters(slug),
  });
  const key = picked ?? list.data?.items[0]?.key ?? null;
  const chapter = useQuery({
    queryKey: ["chapter", slug, key],
    queryFn: () => api.chapter(slug, key ?? ""),
    enabled: key !== null,
  });

  return (
    <section className="chapter-preview" aria-label="章节正文预览">
      <h2>章节正文</h2>
      {list.isLoading && <p className="event-track-empty">正在读取章节列表。</p>}
      {list.error && (
        <p className="event-track-empty">章节列表读不出来：{list.error.message}</p>
      )}
      {list.data && list.data.items.length === 0 && (
        <p className="event-track-empty">这门课还没有章节。</p>
      )}
      {list.data && list.data.items.length > 0 && (
        <>
          <div className="chapter-picker" role="tablist" aria-label="章节">
            {list.data.items.map((item) => (
              <button
                type="button"
                role="tab"
                key={item.key}
                aria-selected={item.key === key}
                className={item.key === key ? "active" : ""}
                onClick={() => setPicked(item.key)}
              >
                第 {item.number} 章
              </button>
            ))}
          </div>
          {chapter.isLoading && <p className="event-track-empty">正在读取章节正文。</p>}
          {chapter.error && (
            <p className="event-track-empty">
              章节正文读不出来：{chapter.error.message}
            </p>
          )}
          {chapter.data && (
            <article className="chapter-body">
              <h3>{chapter.data.key}</h3>
              <p className="chapter-meta">
                有效字符{" "}
                {authoritativeEffectiveChars(
                  SNAPSHOT_CHARS,
                  effectiveCharCount(chapter.data.content),
                ).toLocaleString()}
                {" · "}
                {chapter.data.path}
              </p>
              <Markdown>{chapter.data.content}</Markdown>
            </article>
          )}
        </>
      )}
    </section>
  );
}

/**
 * The workbench of one run.
 *
 * @returns The page of the run, or the reason why there is no page.
 */
export function RunWorkspace() {
  const { runId = "" } = useParams();
  const [pickedStep, setPickedStep] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.run(runId),
    refetchInterval: (query) =>
      shouldPollRun(query.state.data?.run) ? 1200 : false,
  });

  if (detail.isLoading) {
    return <p className="notice">正在读取这条 Run。</p>;
  }
  if (detail.error) {
    return (
      <p className="notice error">
        这条 Run 读不出来：{detail.error.message}
        <br />
        <Link className="primary-action" to="/runs">
          回到运行列表
        </Link>
      </p>
    );
  }
  if (!detail.data) {
    return <p className="notice">这条 Run 还没有内容。</p>;
  }

  const run = detail.data.run;
  const selectedStep = pickedStep ?? run.current_step;
  const stage = detail.data.workflow_steps.find(
    (step) => step.id === selectedStep,
  );

  return (
    <div className="run-workspace">
      <header className="page-intro">
        <p className="eyebrow">Run workspace</p>
        <h1>这条 Run 走到哪一步了</h1>
        <p className="workspace-slug">{run.id}</p>
        <dl className="workspace-facts">
          <div>
            <dt>状态</dt>
            <dd>{run.status}</dd>
          </div>
          <div>
            <dt>当前阶段</dt>
            <dd>{run.current_step}</dd>
          </div>
          <div>
            <dt>课程</dt>
            <dd>
              <Link to={`/courses/${run.course_slug}`}>{run.course_slug}</Link>
            </dd>
          </div>
        </dl>
        {run.error_message && <p className="notice error">{run.error_message}</p>}
      </header>

      <WorkflowMap
        steps={detail.data.workflow_steps}
        currentStep={run.current_step}
        selectedStep={selectedStep}
        onSelect={setPickedStep}
      />

      {stage && (
        <section className="run-stage" aria-label="阶段说明">
          <h2>{stage.title}</h2>
          <p>{stage.description}</p>
          <dl>
            <dt>需要人给的</dt>
            <dd>{stage.user_input}</dd>
            <dt>这一步产出</dt>
            <dd>{stage.model_output}</dd>
          </dl>
        </section>
      )}

      <LiveAgentActivity step={run.current_step} events={detail.data.events} />

      <EventTrack events={detail.data.events} />

      <ChapterPreview slug={run.course_slug} />
    </div>
  );
}

/**
 * The list of the runs.
 *
 * The list is the way into the workbench: every run says which run it is
 * and where it stands, and every run links to its own page.
 *
 * @returns The page with the list of the runs.
 */
export function RunList() {
  const runs = useQuery({
    queryKey: ["runs"],
    queryFn: () => api.runs(),
  });

  return (
    <div className="run-list">
      <header className="page-intro">
        <p className="eyebrow">Runs</p>
        <h1>运行记录</h1>
        <p>每一次建课都会在账上留下一条 Run。</p>
      </header>
      {runs.isLoading && <p className="notice">正在读取运行记录。</p>}
      {runs.error && (
        <p className="notice error">运行记录读不出来：{runs.error.message}</p>
      )}
      {runs.data && runs.data.items.length === 0 && (
        <p className="notice">还没有任何 Run。</p>
      )}
      {runs.data && runs.data.items.length > 0 && (
        <ul className="run-list-items">
          {runs.data.items.map((item) => (
            <li key={item.id}>
              <Link to={`/runs/${item.id}`}>
                <strong>{item.course_slug}</strong>
                <span className="run-list-status">{item.status}</span>
                <span className="run-list-step">{item.current_step}</span>
                <time dateTime={item.created_at}>
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
