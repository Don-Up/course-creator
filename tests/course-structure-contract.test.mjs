import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { basename, join, resolve } from "node:path";
import {
  analyzeCourse,
  analyzeLesson,
  normalizeReferenceHeading,
} from "../scripts/lib/course-structure-contract.mjs";
import { disclosureViolations } from "../scripts/lib/disclosure-contract.mjs";

const sha256 = (value) => createHash("sha256").update(value).digest("hex");

test("returns every level-2 candidate without deciding its semantic role", () => {
  const markdown = `# 第 4 章\n\n> 预计学习时间：60 分钟  \n> 一句话总结：完成本章。\n\n## 十三、参考文献\n\n- [Ollama](https://ollama.com/)\n`;
  const report = analyzeLesson(markdown, "lessons/04.md");
  assert.equal(report.diagnostics.some((item) => item.code === "REFERENCE_SECTION_MISSING"), true);
  assert.deepEqual(report.referenceCandidates.map((item) => item.title), ["十三、参考文献"]);
  assert.equal(report.referenceCandidates[0].externalLinkCount, 1);
});

test("collects intro and reference violations in one report", () => {
  const markdown = `# 第 1 章\n\n预计学习时间：60 分钟\n\n一句话总结：完成本章。\n\n## 本章参考文献\n\n- 来源\n`;
  const report = analyzeLesson(markdown, "lessons/01.md");
  assert.deepEqual(
    report.diagnostics.map((item) => item.code).sort(),
    ["INTRO_NON_CANONICAL", "REFERENCE_SECTION_MISSING"],
  );
});

test("normalizes only the selected AST node and is idempotent", () => {
  const markdown = `# 第 4 章\n\n> 预计学习时间：60 分钟  \n> 一句话总结：完成本章。\n\n## 十三、参考文献\n\n- 来源\n`;
  const report = analyzeLesson(markdown, "lessons/04.md");
  const nodeId = report.referenceCandidates[0].nodeId;
  const patched = normalizeReferenceHeading(markdown, nodeId, sha256(markdown));
  assert.match(patched.markdown, /\n## 参考文献\n/);
  assert.equal(analyzeLesson(patched.markdown, "lessons/04.md").diagnostics.length, 0);
  assert.equal(
    normalizeReferenceHeading(patched.markdown, nodeId, sha256(patched.markdown)).changed,
    false,
  );
});

test("rejects a stale source hash before changing a node", () => {
  const markdown = `# 标题\n\n> 预计学习时间：30 分钟  \n> 一句话总结：完成本章。\n\n## 来源\n\n- 来源\n`;
  const nodeId = analyzeLesson(markdown, "lessons/01.md").referenceCandidates[0].nodeId;
  assert.throws(
    () => normalizeReferenceHeading(markdown, nodeId, "0".repeat(64)),
    /哈希/,
  );
});

test("offers short paragraph labels before a link list as open-vocabulary candidates", () => {
  const markdown = `# 标题\n\n> 预计学习时间：30 分钟  \n> 一句话总结：完成本章。\n\n## 收束\n\n正文。\n\n**本章使用的资料来源**：\n\n- [官方文档](https://example.com)\n`;
  const report = analyzeLesson(markdown, "lessons/09.md");
  const candidate = report.referenceCandidates.find((item) => item.title.includes("本章使用"));
  assert.ok(candidate);
  const patched = normalizeReferenceHeading(markdown, candidate.nodeId, sha256(markdown));
  assert.match(patched.markdown, /\n## 参考文献\n\n- \[官方文档]/);
});

test("reports external links before the canonical reference section from the shared contract", () => {
  const markdown = `# 标题\n\n> 预计学习时间：30 分钟  \n> 一句话总结：完成本章。\n\n## 正文\n\n[外链](https://example.com)\n\n## 参考文献\n\n- 来源\n`;
  const report = analyzeLesson(markdown, "lessons/01.md");
  assert.deepEqual(report.diagnostics.map((item) => item.code), ["EXTERNAL_LINK_BEFORE_REFERENCES"]);
});

test("course scan and builder preflight report every malformed lesson", (context) => {
  const repositoryRoot = resolve(import.meta.dirname, "..");
  const courseRoot = mkdtempSync(join(repositoryRoot, "courses", "contract-test-"));
  context.after(() => rmSync(courseRoot, { recursive: true, force: true }));
  mkdirSync(join(courseRoot, "lessons"));
  mkdirSync(join(courseRoot, "reference"));
  writeFileSync(join(courseRoot, "reference", "glossary.md"), "| 术语 | 定义 |\n|---|---|\n");
  const lesson = (title) => `# 标题\n\n> 预计学习时间：30 分钟  \n> 一句话总结：总结。\n\n## ${title}\n\n- 来源\n`;
  writeFileSync(join(courseRoot, "lessons", "01.md"), lesson("本章参考文献"));
  writeFileSync(join(courseRoot, "lessons", "02.md"), lesson("十三、参考文献"));
  writeFileSync(join(courseRoot, "course.json"), JSON.stringify({
    slug: basename(courseRoot), title: "Contract", lessons: [
      { number: 1, title: "标题", status: "available", markdown: "lessons/01.md", href: "lessons/01.html" },
      { number: 2, title: "标题", status: "available", markdown: "lessons/02.md", href: "lessons/02.html" },
    ],
  }));

  const scan = analyzeCourse(courseRoot);
  assert.deepEqual(
    scan.diagnostics.filter((item) => item.code === "REFERENCE_SECTION_MISSING").map((item) => item.path),
    ["lessons/01.md", "lessons/02.md"],
  );
  const build = spawnSync(process.execPath, ["scripts/build-static-course.mjs", basename(courseRoot)], {
    cwd: repositoryRoot, encoding: "utf8",
  });
  assert.equal(build.status, 1);
  assert.match(build.stderr, /COURSE_STRUCTURE_PREFLIGHT_FAILED/);
  assert.match(build.stderr, /lessons\/01\.md/);
  assert.match(build.stderr, /lessons\/02\.md/);
});

test("normalize CLI accepts a file inside its course and rejects stale hashes", (context) => {
  const repositoryRoot = resolve(import.meta.dirname, "..");
  const courseRoot = mkdtempSync(join(repositoryRoot, "courses", "contract-cli-"));
  context.after(() => rmSync(courseRoot, { recursive: true, force: true }));
  mkdirSync(join(courseRoot, "lessons"));
  const file = join(courseRoot, "lessons", "01.md");
  const markdown = `# 标题\n\n> 预计学习时间：30 分钟  \n> 一句话总结：完成。\n\n## 本章资料\n\n- [来源](https://example.com)\n`;
  writeFileSync(file, markdown);
  const nodeId = analyzeLesson(markdown).referenceCandidates.at(-1).nodeId;
  const result = spawnSync(process.execPath, [
    "scripts/course-structure-contract.mjs", "normalize-reference",
    "--course", courseRoot, "--file", file, "--node", nodeId,
    "--expected-hash", sha256(markdown),
  ], { cwd: repositoryRoot, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
});

test("public model terminology is not mistaken for internal distillation disclosure", () => {
  assert.deepEqual(
    disclosureViolations("配置 Qwen2.5/DeepSeek-R1 蒸馏版 LLM"),
    [],
  );
  assert.deepEqual(
    disclosureViolations("本章内容来自内部材料蒸馏来源"),
    ["内部材料", "蒸馏来源"],
  );
});

test("teaching dialogue is not mistaken for production-side user material", () => {
  assert.deepEqual(
    disclosureViolations("请确认你提供的是 `git log` 的输出；如果是 Jira 列表，请换用对应的 SKILL。"),
    [],
  );
  assert.deepEqual(
    disclosureViolations("本章基于你提供的材料整理，请先阅读内部材料。"),
    ["你提供的材料", "内部材料"],
  );
});
