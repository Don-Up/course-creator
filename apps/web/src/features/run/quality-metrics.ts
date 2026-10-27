/**
 * The two numbers the workspace shows about a chapter.
 *
 * A chapter has two numbers that look alike and are not the same thing:
 *
 * - The **live** number is what the text on the disk says right now.  It
 *   is measured from the Markdown of the chapter, with the syntax of the
 *   Markdown left out.
 * - The **authoritative** number is what the quality snapshot says.  The
 *   snapshot is written atomically and is the current fact about the
 *   quality of the course; the artifacts of a run are the history of
 *   that quality, and they are only a fallback for the courses that were
 *   built before the snapshot existed.
 *
 * The rule of the project is that the snapshot wins.  When the two
 * numbers disagree, the workspace shows the number of the snapshot, so
 * the workbench never shows two numbers that contradict each other.
 */

/**
 * Count the characters of a Markdown text that count as content.
 *
 * The syntax of the Markdown is not content: a fenced code block, an
 * image, the address of a link and the marks of the Markdown itself are
 * not words of the chapter.  The count that comes back is therefore the
 * one that can be compared with the minimum the intake form asked for.
 *
 * @param markdown The text of the chapter, for example "# 第一课\n\n正文。".
 * @returns The number of characters that count as content, for example 4.
 */
export function effectiveCharCount(markdown: string): number {
  let value = markdown.replace(/```[\s\S]*?```/g, "");
  value = value.replace(/!\[[^\]]*]\([^)]+\)/g, "");
  value = value.replace(/\[([^\]]+)]\([^)]+\)/g, "$1");
  value = value.replace(/[#>*_`|~\-\s]/g, "");
  return value.length;
}

/**
 * Decide which number of a chapter the workspace shows.
 *
 * The snapshot is the current fact and it wins.  The fallback is the
 * live text of the chapter, and it is used only when there is no
 * snapshot to be had: a course that has not been through the quality
 * stage has no snapshot yet, and showing nothing would be worse than
 * showing the text that is really there.
 *
 * @param snapshotChars The number of the quality snapshot, or `undefined`
 *   when the course has no snapshot yet.
 * @param fallbackChars The number measured from the text of the chapter,
 *   for example 12345.
 * @returns The number of the snapshot when there is one, and the number
 *   of the fallback otherwise.
 */
export function authoritativeEffectiveChars(
  snapshotChars: number | undefined,
  fallbackChars: number,
): number {
  return typeof snapshotChars === "number" ? snapshotChars : fallbackChars;
}
