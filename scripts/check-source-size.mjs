import { readdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";

const MAX_LINES = 500;
const sourceRoots = ["apps/api/app", "apps/web/src"];
const extensions = new Set([".py", ".ts", ".tsx", ".css"]);

async function collectFiles(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) files.push(...await collectFiles(path));
    else if (extensions.has(entry.name.slice(entry.name.lastIndexOf(".")))) files.push(path);
  }
  return files;
}

const files = (await Promise.all(sourceRoots.map(collectFiles))).flat();
const violations = [];
for (const file of files) {
  const source = await readFile(file, "utf8");
  const lines = source.split("\n").length - (source.endsWith("\n") ? 1 : 0);
  if (lines > MAX_LINES) violations.push({ file: relative(process.cwd(), file), lines });
}

if (violations.length) {
  console.error(`Production source files must not exceed ${MAX_LINES} lines:`);
  for (const violation of violations.sort((a, b) => b.lines - a.lines)) {
    console.error(`- ${violation.file}: ${violation.lines}`);
  }
  process.exitCode = 1;
} else {
  console.log(`Source size check passed (${files.length} files, <= ${MAX_LINES} lines each).`);
}
