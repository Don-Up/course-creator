import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";

import { RunEventRead } from "../../api";

/**
 * The live view of the stage a run is at.
 *
 * The workspace shows two things about the stage that is running: what
 * happened in it, and how long it has been running.  Both come out of
 * the events of the run, so they survive a refresh of the browser: the
 * events are on the books in the database, not in the page.
 *
 * The events are shown newest first.  The one that matters most is the
 * last one that happened, and a person who opens the workbench wants to
 * read that one first.
 */

/**
 * Write a duration the way a clock writes it.
 *
 * @param milliseconds The duration in milliseconds, for example 65432.
 * @returns The duration as `mm:ss`, or as `h:mm:ss` when it lasts longer
 *   than an hour, for example "01:05".
 */
export function formatElapsed(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  if (hours > 0) {
    return `${hours}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

/**
 * Show how long the current round of a stage has been running.
 *
 * The clock ticks on its own, so the number moves while the person is
 * looking at it.  The timer stops being drawn when the stage is left,
 * because the component is unmounted with it.
 *
 * @param startedAt The moment the stage started, as the API gives it, for
 *   example "2026-10-27T08:31:05.123456+00:00".
 * @returns The element with the running time of the stage.
 */
export function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const started = Date.parse(startedAt);
  const elapsed = Number.isNaN(started) ? "—" : formatElapsed(now - started);
  return <time className="run-elapsed">本轮已运行 {elapsed}</time>;
}

/**
 * The events of one stage, newest first.
 *
 * The list is the trace of the stage: what happened, in which order and
 * when.  It is empty when the stage has not started yet, and the page
 * says so instead of showing an empty box.
 *
 * @param step The id of the stage, for example "generation".
 * @param events The events of the run, in the order the API gives them.
 * @returns The element with the events of the stage.
 */
export function LiveAgentActivity({
  step,
  events,
}: {
  step: string;
  events: RunEventRead[];
}) {
  const relevant = events
    .filter((event) => event.step === step)
    .slice()
    .sort((left, right) => right.seq - left.seq);
  const first = relevant.length ? relevant[relevant.length - 1] : null;

  return (
    <section className="run-activity" aria-label="当前阶段的活动">
      <div className="run-activity-heading">
        <LoaderCircle className="spin" size={15} />
        <strong>当前阶段正在发生的事</strong>
        {first && <ElapsedTimer startedAt={first.created_at} />}
      </div>
      {relevant.length === 0 ? (
        <p className="run-activity-empty">这个阶段还没有留下事件。</p>
      ) : (
        <ol className="run-activity-list">
          {relevant.map((event) => (
            <li key={event.id}>
              <span className="run-activity-type">{event.event_type}</span>
              <span className="run-activity-message">{event.message}</span>
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
