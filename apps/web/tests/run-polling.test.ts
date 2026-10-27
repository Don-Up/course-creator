/**
 * The contract of the polling decision.
 *
 * The browser keeps asking about a run until the run is over and has
 * nothing left to wait for.  The case that is easy to get wrong is the
 * failed run that still carries a command: that run is going to move
 * again, so the polling has to keep going.
 *
 * The test runs on plain node, without a test framework:
 *
 *     node --experimental-strip-types apps/web/tests/run-polling.test.ts
 */
import { shouldPollRun } from "../src/features/run/run-polling.ts";

/**
 * Check one answer of the decision.
 *
 * @param actual What `shouldPollRun` answered.
 * @param expected What it should have answered.
 * @param message What the case is about, printed when the two differ.
 * @returns Nothing. The test fails by throwing when the two differ.
 */
function assertEqual(actual: boolean, expected: boolean, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}（期望 ${expected}，实际 ${actual}）`);
  }
}

// 1. 终态、没有活跃命令：这条 Run 不会再自己变了，停轮询。
assertEqual(
  shouldPollRun({ status: "COMPLETED", active_command: null }),
  false,
  "a completed run with nothing left to wait for must stop polling",
);

// 2. 终态、但有活跃命令：从检查点继续，答案还没定，轮询要继续。
assertEqual(
  shouldPollRun({ status: "FAILED", active_command: { status: "PENDING" } }),
  true,
  "a failed run with an open command must keep polling",
);

// 3. 非终态：还在跑，轮询要继续。
assertEqual(
  shouldPollRun({ status: "RUNNING" }),
  true,
  "a running run must keep polling",
);

// 4. 还没拿到这条 Run：再问一次才能拿到，轮询要继续。
assertEqual(
  shouldPollRun(undefined),
  true,
  "a run that has not been loaded yet must keep polling",
);

console.log("run-polling：4 条断言全过");
