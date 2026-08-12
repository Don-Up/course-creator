#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, relative, sep, isAbsolute } from "node:path";
import { analyzeCourse, normalizeReferenceHeading } from "./lib/course-structure-contract.mjs";

function option(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : null;
}

function within(root, target) {
  const rel = relative(root, target);
  return Boolean(rel) && !rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel);
}

try {
  const command = process.argv[2];
  if (command === "scan") {
    const courseRoot = resolve(option("--course") || "");
    const lessonPaths = process.argv.flatMap((value, index) => value === "--lesson" ? [process.argv[index + 1]] : []);
    process.stdout.write(JSON.stringify(analyzeCourse(courseRoot, lessonPaths.length ? lessonPaths : null)));
  } else if (command === "normalize-reference") {
    const file = resolve(option("--file") || "");
    const courseRoot = resolve(option("--course") || resolve(file, "../.."));
    if (!within(courseRoot, file)) throw new Error("目标文件不在课程目录内");
    const markdown = readFileSync(file, "utf8");
    const result = normalizeReferenceHeading(markdown, option("--node"), option("--expected-hash"));
    if (result.changed) writeFileSync(file, result.markdown, "utf8");
    process.stdout.write(JSON.stringify({ ...result, markdown: undefined }));
  } else {
    throw new Error("用法：scan --course <root> 或 normalize-reference --course <root> --file <file> --node <id> --expected-hash <sha256>");
  }
} catch (error) {
  process.stderr.write(JSON.stringify({ error: error.message }));
  process.exitCode = 2;
}
