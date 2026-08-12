import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fromMarkdown } from "mdast-util-from-markdown";

const CANONICAL_REFERENCE_TITLE = "参考文献";

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const posix = (value) => value.replaceAll("\\", "/");

function headingText(node, markdown) {
  return markdown.slice(node.position.start.offset, node.position.end.offset)
    .replace(/^#{1,6}\s+/, "")
    .replace(/\s+#+\s*$/, "")
    .trim();
}

function textFromNode(node, markdown) {
  return markdown.slice(node.position.start.offset, node.position.end.offset).trim();
}

function sectionChildren(children, index) {
  const result = [];
  for (let cursor = index + 1; cursor < children.length; cursor += 1) {
    const child = children[cursor];
    if (child.type === "heading" && child.depth <= 2) break;
    result.push(child);
  }
  return result;
}

function countExternalLinks(nodes) {
  let count = 0;
  const visit = (node) => {
    if (node.type === "link" && /^https?:\/\//i.test(node.url || "")) count += 1;
    for (const child of node.children || []) visit(child);
  };
  for (const node of nodes) visit(node);
  return count;
}

function canonicalIntro(children, markdown, titleIndex) {
  const afterTitle = children.slice(titleIndex + 1);
  const first = afterTitle[0];
  if (!first || first.type !== "blockquote") return null;
  const raw = textFromNode(first, markdown);
  const lines = raw.split(/\r?\n/).map((line) => line.replace(/^>\s?/, "").trim()).filter(Boolean);
  if (lines.length !== 2 || !lines[0].startsWith("预计学习时间：") || !lines[1].startsWith("一句话总结：")) return null;
  return {
    time: lines[0].slice("预计学习时间：".length).trim(),
    summary: lines[1].slice("一句话总结：".length).trim(),
    nodeId: `blockquote:${first.position.start.offset}`,
  };
}

export function analyzeLesson(markdown, path = "lesson.md") {
  const tree = fromMarkdown(markdown);
  const children = tree.children || [];
  const titleIndex = children.findIndex((node) => node.type === "heading" && node.depth === 1);
  const titleNode = titleIndex >= 0 ? children[titleIndex] : null;
  const intro = titleNode ? canonicalIntro(children, markdown, titleIndex) : null;
  const diagnostics = [];

  if (!titleNode) {
    diagnostics.push({
      code: "TITLE_MISSING", path, nodeId: null, line: 1, actual: "", expected: "一级标题",
      severity: "error", repairCapability: "structure_heading",
      successCriteria: ["课程章节包含且仅包含一个一级标题"],
    });
  }
  if (!intro) {
    diagnostics.push({
      code: "INTRO_NON_CANONICAL", path,
      nodeId: titleNode ? `heading:${titleNode.position.start.offset}` : null,
      line: titleNode?.position?.start?.line || 1,
      actual: "章首未形成标准引用块", expected: "仅含预计学习时间和一句话总结的引用块",
      severity: "error", repairCapability: "intro_contract",
      successCriteria: ["一级标题后首个节点是引用块", "引用块仅含预计学习时间和一句话总结"],
    });
  }

  const referenceCandidates = [];
  let canonicalReference = null;
  children.forEach((node, index) => {
    if (node.type !== "heading" || node.depth !== 2) return;
    const section = sectionChildren(children, index);
    const title = headingText(node, markdown);
    const candidate = {
      nodeId: `heading:${node.position.start.offset}`,
      depth: 2,
      title,
      line: node.position.start.line,
      relativePosition: markdown.length ? node.position.start.offset / markdown.length : 0,
      childKinds: [...new Set(section.map((item) => item.type))],
      externalLinkCount: countExternalLinks(section),
      excerpt: section.map((item) => textFromNode(item, markdown)).join("\n\n").slice(0, 1600),
    };
    referenceCandidates.push(candidate);
    if (title === CANONICAL_REFERENCE_TITLE) canonicalReference = candidate;
  });
  // A course may express the final section label as a short emphasized
  // paragraph followed by a source list. Expose that structural shape to the
  // semantic classifier without guessing from title vocabulary here.
  children.forEach((node, index) => {
    if (node.type !== "paragraph" || node.position.start.offset / Math.max(markdown.length, 1) < 0.45) return;
    const raw = textFromNode(node, markdown);
    const following = children[index + 1];
    if (!following || following.type !== "list" || raw.length > 100) return;
    const externalLinkCount = countExternalLinks([following]);
    if (!externalLinkCount) return;
    const title = raw.replaceAll("**", "").replaceAll("__", "").replace(/[：:]\s*$/, "").trim();
    referenceCandidates.push({
      nodeId: `paragraph:${node.position.start.offset}`,
      depth: 0,
      title,
      line: node.position.start.line,
      relativePosition: node.position.start.offset / Math.max(markdown.length, 1),
      childKinds: [following.type],
      externalLinkCount,
      excerpt: textFromNode(following, markdown).slice(0, 1600),
    });
  });

  if (canonicalReference) {
    const referenceOffset = Number(canonicalReference.nodeId.split(":")[1]);
    const linksBefore = [];
    const visit = (node) => {
      if (
        node.type === "link" && /^https?:\/\//i.test(node.url || "")
        && node.position?.start?.offset < referenceOffset
      ) linksBefore.push(node);
      for (const child of node.children || []) visit(child);
    };
    visit(tree);
    if (linksBefore.length) {
      diagnostics.push({
        code: "EXTERNAL_LINK_BEFORE_REFERENCES", path,
        nodeId: `link:${linksBefore[0].position.start.offset}`,
        line: linksBefore[0].position.start.line,
        actual: `${linksBefore.length} 个外部链接位于参考文献区块之前`,
        expected: "学生可见外部链接统一位于参考文献区块",
        severity: "error", repairCapability: "link_reference",
        successCriteria: ["参考文献区块前不包含外部链接"],
      });
    }
  }

  if (!canonicalReference) {
    diagnostics.push({
      code: "REFERENCE_SECTION_MISSING", path, nodeId: null,
      line: referenceCandidates.at(-1)?.line || titleNode?.position?.start?.line || 1,
      actual: referenceCandidates.map((item) => item.title).join(" / "), expected: `## ${CANONICAL_REFERENCE_TITLE}`,
      severity: "error", repairCapability: "reference_role_classification",
      successCriteria: [`语义上的参考资料区块标题统一为 ## ${CANONICAL_REFERENCE_TITLE}`],
      candidates: referenceCandidates,
    });
  }

  return {
    schemaVersion: "1.0",
    path,
    hash: sha256(markdown),
    title: titleNode ? headingText(titleNode, markdown) : "",
    intro,
    canonicalReference,
    referenceCandidates,
    diagnostics,
  };
}

export function analyzeCourse(courseRoot, lessonPaths = null) {
  let paths = lessonPaths;
  if (!paths) {
    const descriptorPath = join(courseRoot, "course.json");
    if (existsSync(descriptorPath)) {
      const course = JSON.parse(readFileSync(descriptorPath, "utf8"));
      paths = (course.lessons || []).map((lesson) => lesson.markdown).filter(Boolean);
    } else {
      const lessonsRoot = join(courseRoot, "lessons");
      paths = existsSync(lessonsRoot)
        ? readdirSync(lessonsRoot).filter((name) => name.endsWith(".md")).map((name) => `lessons/${name}`)
        : [];
    }
  }
  const lessons = [];
  const diagnostics = [];
  for (const path of [...new Set(paths)].sort()) {
    const absolute = join(courseRoot, path);
    if (!existsSync(absolute)) continue;
    const report = analyzeLesson(readFileSync(absolute, "utf8"), posix(relative(courseRoot, absolute)));
    lessons.push(report);
    diagnostics.push(...report.diagnostics);
  }
  return { schemaVersion: "1.0", courseRoot, lessons, diagnostics };
}

export function normalizeReferenceHeading(markdown, nodeId, expectedHash) {
  if (sha256(markdown) !== expectedHash) throw new Error("课程源文件哈希已变化，拒绝覆盖");
  const report = analyzeLesson(markdown);
  const candidate = report.referenceCandidates.find((item) => item.nodeId === nodeId);
  if (!candidate) {
    if (report.canonicalReference) return { changed: false, markdown, hash: expectedHash, nodeId };
    throw new Error(`未找到 Markdown AST 节点：${nodeId}`);
  }
  if (candidate.title === CANONICAL_REFERENCE_TITLE) {
    return { changed: false, markdown, hash: expectedHash, nodeId };
  }
  const offset = Number(nodeId.split(":")[1]);
  if (nodeId.startsWith("paragraph:")) {
    const tree = fromMarkdown(markdown);
    const node = tree.children.find(
      (item) => item.type === "paragraph" && item.position?.start?.offset === offset,
    );
    if (!node) throw new Error(`未找到 Markdown AST 节点：${nodeId}`);
    const patched = markdown.slice(0, node.position.start.offset)
      + `## ${CANONICAL_REFERENCE_TITLE}`
      + markdown.slice(node.position.end.offset);
    return { changed: true, markdown: patched, hash: sha256(patched), nodeId };
  }
  const lineEnd = markdown.indexOf("\n", offset);
  const end = lineEnd < 0 ? markdown.length : lineEnd;
  const currentLine = markdown.slice(offset, end);
  const replacement = currentLine.replace(/^(##)\s+.*$/, `$1 ${CANONICAL_REFERENCE_TITLE}`);
  const patched = markdown.slice(0, offset) + replacement + markdown.slice(end);
  return { changed: true, markdown: patched, hash: sha256(patched), nodeId };
}
