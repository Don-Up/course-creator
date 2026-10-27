/**
 * The contract of the quality numbers of a chapter.
 *
 * A chapter has two numbers that look alike: the live text of the
 * chapter and the quality snapshot of the course.  The rule of the
 * project is that the snapshot wins, so the workbench never shows two
 * numbers that contradict each other.  The fallback is only used when
 * there is no snapshot at all.
 *
 * The test runs on plain node, without a test framework:
 *
 *     node --experimental-strip-types apps/web/tests/quality-metrics.test.ts
 */
import {
  authoritativeEffectiveChars,
  effectiveCharCount,
} from "../src/features/run/quality-metrics.ts";

/**
 * Check one answer of a decision.
 *
 * @param actual What the function answered.
 * @param expected What it should have answered.
 * @param message What the case is about, printed when the two differ.
 * @returns Nothing. The test fails by throwing when the two differ.
 */
function assertEqual(actual: number, expected: number, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}（期望 ${expected}，实际 ${actual}）`);
  }
}

// 1. 有快照：快照说了算，正文算出来的数字不算数。
assertEqual(
  authoritativeEffectiveChars(12000, 9999),
  12000,
  "the snapshot must win over the fallback",
);

// 2. 没有快照：用正文的数字，不显示空白。
assertEqual(
  authoritativeEffectiveChars(undefined, 9999),
  9999,
  "without a snapshot the fallback must be used",
);

// 3. 快照是 0 也是数：0 是有效的数字，不是"没有"。
assertEqual(
  authoritativeEffectiveChars(0, 9999),
  0,
  "a snapshot of zero is a number and must win",
);

// 4. 有效字符：Markdown 的记号不算正文，代码块与图片也不算。
assertEqual(
  effectiveCharCount("# 标题\n\n正文内容"),
  6,
  "the marks of the markdown must not count as content",
);

console.log("quality-metrics：4 条断言全过");
