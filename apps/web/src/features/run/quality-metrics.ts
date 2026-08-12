export function authoritativeEffectiveChars(
  snapshotChars: number | undefined,
  fallbackChars: number,
): number {
  return typeof snapshotChars === "number" ? snapshotChars : fallbackChars;
}
