import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_LINES = 500;
const sourceRoots = ["apps/api/app", "apps/web/src"];
const extensions = new Set([".py", ".ts", ".tsx", ".css"]);

// The repo root comes from the script's own location, never from
// `process.cwd()`: the gate must scan the same directories and print the same
// paths no matter which directory it was started from.
const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));

function collectFiles(root) {
  let entries;
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch (error) {
    // A root that does not exist yet counts as zero files.  Crashing with a
    // stack trace would bury the message the gate exists to deliver.
    if (error?.code === "ENOENT") {
      return [];
    }
    throw error;
  }

  const files = [];
  for (const entry of entries) {
    const fullPath = join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath));
    } else if (extensions.has(extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

function countLines(source) {
  return source.split("\n").length - (source.endsWith("\n") ? 1 : 0);
}

const violations = [];
let scannedFiles = 0;

for (const sourceRoot of sourceRoots) {
  for (const file of collectFiles(join(repoRoot, sourceRoot))) {
    scannedFiles += 1;
    const lines = countLines(readFileSync(file, "utf8"));
    if (lines > MAX_LINES) {
      violations.push({
        // POSIX separators keep the report identical on every platform.
        file: relative(repoRoot, file).split(sep).join("/"),
        lines,
      });
    }
  }
}

if (violations.length > 0) {
  console.log(`Production source files must not exceed ${MAX_LINES} lines:`);
  for (const violation of violations.sort((a, b) => b.lines - a.lines)) {
    console.log(`- ${violation.file}: ${violation.lines}`);
  }
  process.exitCode = 1;
} else {
  console.log(`Source size check passed (${scannedFiles} files, <= ${MAX_LINES} lines each).`);
}
