type RunPollingState = {
  status?: string | null;
  active_command?: { status?: string | null } | null;
};

const terminalRunStatuses = new Set(["COMPLETED", "FAILED", "STOPPED"]);

export function shouldPollRun(run: RunPollingState | undefined): boolean {
  return !terminalRunStatuses.has(run?.status || "") || Boolean(run?.active_command);
}
