/**
 * Whether the browser should keep asking about a run.
 *
 * The read model of P2.5 answers two things a person needs to decide this:
 * the status of the run, and the command the run is still waiting on when
 * there is one.  The decision has two halves, and the second one is the
 * one that is easy to get wrong.
 *
 * - A run that is over (`COMPLETED`, `FAILED` or `STOPPED`) stops the
 *   polling, because nothing about it will change on its own.
 * - A run that is over **but still carries an active command** keeps the
 *   polling.  That is the "continue from the checkpoint" case: the run
 *   failed, a command was queued, and the answer is not final yet.
 *
 * A run that has not been loaded yet is polled as well, because asking
 * once more is how it gets loaded.
 *
 * The statuses are the ones the contract freezes in RoadMap section 2.1.
 * `WAITING_APPROVAL` is deliberately not one of them: a run that waits
 * for a person is not over, it is waiting to be let go.
 */

/**
 * The part of a run the decision looks at.
 *
 * The shape is a part of the read model of P2.5, not a copy of it, so the
 * frontend does not have to hold the whole run to ask this question.
 */
export type RunPollingState = {
  status?: string | null;
  active_command?: { status?: string | null } | null;
};

/**
 * The statuses of a run that mean it is over.
 *
 * A run in one of these is done unless it still carries a command.
 */
export const TERMINAL_RUN_STATUSES = new Set(["COMPLETED", "FAILED", "STOPPED"]);

/**
 * Decide whether the browser should ask about this run again.
 *
 * @param run The run as the read model of P2.5 gives it, or `undefined`
 *   when the run has not been loaded yet.
 * @returns `true` when the answer can still change, `false` when the run is
 *   over and has nothing left to wait for.
 */
export function shouldPollRun(run: RunPollingState | undefined): boolean {
  const status = run?.status || "";
  if (!TERMINAL_RUN_STATUSES.has(status)) {
    return true;
  }
  return Boolean(run?.active_command);
}
