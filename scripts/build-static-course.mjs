import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { analyzeCourse, analyzeLesson } from "./lib/course-structure-contract.mjs";
import { disclosureFindings } from "./lib/disclosure-contract.mjs";

const root = process.cwd();
const courseSlug = process.argv[2];
if (!courseSlug) throw new Error("用法: node scripts/build-static-course.mjs <course-slug>");
const chapterArgument = process.argv.indexOf("--chapters");
if (chapterArgument >= 0 && !process.argv[chapterArgument + 1]) {
  throw new Error("--chapters 缺少章节编号，例如 1,2,3");
}
const selectedChapterNumbers = chapterArgument >= 0
  ? new Set(
      process.argv[chapterArgument + 1]
        .split(",")
        .map((value) => Number(value.trim()))
        .filter((value) => Number.isInteger(value) && value > 0),
    )
  : null;

const courseRoot = join(root, "courses", courseSlug);
const lessonsRoot = join(courseRoot, "lessons");
const referenceRoot = join(courseRoot, "reference");
const markdownRoot = join(courseRoot, "markdown");
const course = JSON.parse(readFileSync(join(courseRoot, "course.json"), "utf8"));
const contractLessonPaths = (course.lessons || [])
  .filter((lesson) => lesson.markdown && (!selectedChapterNumbers || selectedChapterNumbers.has(Number(lesson.number))))
  .map((lesson) => lesson.markdown);
const structureReport = analyzeCourse(courseRoot, contractLessonPaths);
const structureErrors = structureReport.diagnostics.filter((item) => item.severity === "error");
if (structureErrors.length) {
  console.error(JSON.stringify({
    code: "COURSE_STRUCTURE_PREFLIGHT_FAILED",
    message: `课程结构预检发现 ${structureErrors.length} 个错误`,
    diagnostics: structureErrors,
  }, null, 2));
  process.exit(1);
}
const mermaidUrl = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
const assetVersion = Date.now().toString(36);
const lessonLabel = (lesson) => lesson.code || `第 ${lesson.number} 章`;
const publicationLabel = course.status === "published" ? "已发布" : "人工审核稿";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function stripMarkdown(value) {
  return String(value)
    .replace(/\[\[([^\]|]+)(?:\|[^\]]+)?\]\]/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`]/g, "")
    .trim();
}

function parseTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function loadGlossary() {
  const lines = readFileSync(join(referenceRoot, "glossary.md"), "utf8").split(/\r?\n/);
  const terms = new Map();
  for (let index = 0; index < lines.length - 1; index += 1) {
    if (!/^\|.+\|$/.test(lines[index]) || !/^\|\s*:?-+/.test(lines[index + 1])) continue;
    if (!parseTableRow(lines[index]).includes("术语")) continue;
    index += 2;
    while (index < lines.length && /^\|.+\|$/.test(lines[index])) {
      const [term, definition] = parseTableRow(lines[index]);
      if (term && definition) {
        terms.set(stripMarkdown(term), stripMarkdown(definition));
        const alias = stripMarkdown(term).split(/[（(]/)[0].trim();
        if (alias) terms.set(alias, stripMarkdown(definition));
      }
      index += 1;
    }
  }
  return terms;
}

const glossary = loadGlossary();

function inlineMarkdown(source) {
  const tokens = [];
  const protect = (html) => {
    const marker = `\u0000TOKEN${tokens.length}\u0000`;
    tokens.push(html);
    return marker;
  };
  let value = String(source);
  value = value.replace(/`([^`\n]+)`/g, (_, code) => protect(`<code>${escapeHtml(code)}</code>`));
  value = value.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) => protect(`<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy">`));
  value = value.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
    const external = /^https?:\/\//i.test(href);
    return protect(`<a href="${escapeHtml(href)}"${external ? ' target="_blank" rel="noreferrer"' : ""}>${escapeHtml(label)}</a>`);
  });
  value = value.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, term, label) => {
    const tip = glossary.get(term) || "课程术语，详见术语表。";
    return protect(`<span class="term" tabindex="0" data-tip="${escapeHtml(tip)}">${escapeHtml(label || term)}</span>`);
  });
  value = escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
  return value.replace(/\u0000TOKEN(\d+)\u0000/g, (_, index) => tokens[Number(index)]);
}

function isTableSeparator(line = "") {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line.trim());
}

function isBlockStart(lines, index) {
  const line = lines[index] || "";
  if (!line.trim() || /^```/.test(line) || /^#{2,6}\s/.test(line) || /^>\s?/.test(line)) return true;
  if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+\.\s+/.test(line) || /^\s*(---+|\*\*\*+)\s*$/.test(line)) return true;
  return line.includes("|") && isTableSeparator(lines[index + 1] || "");
}

function headingId(title, counter) {
  return stripMarkdown(title)
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-|-$/g, "") || `section-${counter}`;
}

function renderBlocks(markdown) {
  const lines = markdown.split(/\r?\n/);
  const html = [];
  const toc = [];
  let index = 0;
  let headingCounter = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }

    const fence = line.match(/^```([^\s]*)\s*$/);
    if (fence) {
      const language = fence[1] || "text";
      const code = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) code.push(lines[index++]);
      if (index >= lines.length) throw new Error("Markdown 代码围栏未闭合");
      index += 1;
      if (language.toLowerCase() === "mermaid") {
        html.push(`<figure class="diagram-card"><pre class="mermaid">${escapeHtml(code.join("\n"))}</pre><figcaption>图中关系须结合相邻正文与来源理解。</figcaption></figure>`);
      } else {
        html.push(`<figure class="code-card"><div class="code-toolbar"><span>${escapeHtml(language)}</span><button class="copy-code" type="button">复制</button></div><pre><code data-language="${escapeHtml(language)}">${escapeHtml(code.join("\n"))}</code></pre></figure>`);
      }
      continue;
    }

    const heading = line.match(/^(#{2,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const title = heading[2].trim();
      const id = headingId(title, ++headingCounter);
      toc.push({ level, title: stripMarkdown(title), id });
      html.push(`<h${level} id="${escapeHtml(id)}">${inlineMarkdown(title)}</h${level}>`);
      index += 1;
      continue;
    }

    if (line.includes("|") && isTableSeparator(lines[index + 1] || "")) {
      const headers = parseTableRow(line);
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) rows.push(parseTableRow(lines[index++]));
      html.push(`<div class="table-wrap"><table><thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ""));
      html.push(`<blockquote><p>${inlineMarkdown(quote.join(" "))}</p></blockquote>`);
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-*+]\s+/, ""));
      html.push(`<ul>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*\d+\.\s+/, ""));
      html.push(`<ol>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ol>`);
      continue;
    }

    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) { html.push("<hr>"); index += 1; continue; }

    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) paragraph.push(lines[index++].trim());
    if (!paragraph.length) paragraph.push(lines[index++]);
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
  }
  return { html: html.join("\n"), toc };
}

function parseLesson(markdown, file) {
  const contract = analyzeLesson(markdown, file);
  const lines = markdown.split(/\r?\n/);
  const titleIndex = lines.findIndex((line) => /^#\s+/.test(line));
  if (titleIndex < 0) throw new Error(`${file} 缺少一级标题`);
  const title = lines[titleIndex].replace(/^#\s+/, "").trim();
  let index = titleIndex + 1;
  while (index < lines.length && !lines[index].trim()) index += 1;
  const intro = [];
  while (index < lines.length && /^>\s?/.test(lines[index])) intro.push(lines[index++].replace(/^>\s?/, "").trim());
  const time = contract.intro.time;
  const summary = contract.intro.summary;
  return { title, time, summary, ...renderBlocks(lines.slice(index).join("\n")) };
}

function topbar(prefix = "..") {
  return `<header class="topbar"><a class="brand" href="${prefix}/index.html">${escapeHtml(course.title)}</a><nav><a href="${prefix}/index.html">课程目录</a><a href="${prefix}/reference/glossary.html">术语表</a></nav></header>`;
}

// CHANGED: use local numbering (1, 1.1, 2, 2.1...) instead of global lesson number
function tocHtml(items) {
  let h2Counter = 0;
  let h3Counter = 0;
  const numbered = items.map((item) => {
    if (item.level === 2) { h2Counter++; h3Counter = 0; return { ...item, num: `${h2Counter}` }; }
    if (item.level === 3) { h3Counter++; return { ...item, num: `${h2Counter}.${h3Counter}` }; }
    return item;
  });
  return `<aside class="toc"><strong>本章目录</strong>${numbered.filter((item) => item.level <= 3).map((item) => `<a class="${item.level === 3 ? "sub" : ""}" href="#${escapeHtml(item.id)}"><span class="toc-num">${item.num || ""}</span>${escapeHtml(item.title)}</a>`).join("")}</aside>`;
}

function lessonNavigation(lesson) {
  const available = course.lessons.filter((item) => item.status === "available");
  const current = available.findIndex((item) => item.number === lesson.number);
  const previous = available[current - 1];
  const next = available[current + 1];
  return `<nav class="lesson-nav">${previous ? `<a href="../${previous.href}">← ${escapeHtml(lessonLabel(previous))}<br><strong>${escapeHtml(previous.title)}</strong></a>` : "<span></span>"}${next ? `<a href="../${next.href}">${escapeHtml(lessonLabel(next))} →<br><strong>${escapeHtml(next.title)}</strong></a>` : `<a href="../index.html">返回课程目录 →</a>`}</nav>`;
}

function chapterNavHtml(lesson) {
  let modules = course.modules || [];
  if (modules.length === 0) {
    // Fall back to grouping by lesson.module field
    const moduleNames = [...new Set(course.lessons.map((l) => l.module).filter(Boolean))];
    modules = moduleNames.map((title) => ({ title }));
  }
  if (modules.length === 0) return "";
  const available = course.lessons.filter((l) => l.status === "available");
  const currentIdx = available.findIndex((l) => l.number === lesson.number);
  const position = currentIdx >= 0 ? `${escapeHtml(String(currentIdx + 1))} / ${escapeHtml(String(available.length))}` : "";
  const sections = modules.map((mod) => {
    const modLessons = course.lessons.filter((l) => (
      (mod.chapterNumbers?.includes(l.number)
        || (mod.prefix && l.code?.startsWith(mod.prefix))
        || (!mod.chapterNumbers && !mod.prefix && l.module === mod.title))
      && l.status === "available"
    ));
    if (modLessons.length === 0) return "";
    const links = modLessons.map((l) => {
      const isCurrent = l.number === lesson.number;
      return `<a href="../${escapeHtml(l.href)}"${isCurrent ? ' class="is-current" aria-current="page"' : ""}><span class="chapter-nav-code">${escapeHtml(l.code || "")}</span><span class="chapter-nav-title">${escapeHtml(l.title)}</span></a>`;
    }).join("");
    return `<section class="chapter-nav-module"><h2>${escapeHtml(mod.title)}</h2>${links}</section>`;
  }).filter(Boolean).join("\n");
  return `<aside class="chapter-nav" aria-label="课程章节导航"><button class="chapter-nav-toggle" type="button" aria-expanded="true" aria-controls="chapter-nav-content"><span aria-hidden="true">◀</span><span class="chapter-nav-toggle-label">收起</span></button><div class="chapter-nav-content" id="chapter-nav-content"><div class="chapter-nav-heading"><strong>课程章节</strong>${position ? `<span>第 ${position} 章</span>` : ""}</div><nav class="chapter-nav-list">${sections}</nav></div></aside>`;
}

function renderLesson(lesson) {
  const source = join(courseRoot, lesson.markdown);
  const markdown = readFileSync(source, "utf8");
  const parsed = parseLesson(markdown, relative(root, source));
  const expected = stripMarkdown(parsed.title).replace(/^第\s*\d+\s*章[　\s]*/, "");
  if (expected !== lesson.title) throw new Error(`${lesson.markdown} 标题与 course.json 不一致`);
  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="${escapeHtml(parsed.summary)}"><title>${escapeHtml(lesson.title)} | ${escapeHtml(course.title)}</title><script src="../assets/theme-switcher.js?v=${assetVersion}"></script><link rel="stylesheet" href="../assets/course.css?v=${assetVersion}"><script defer src="${mermaidUrl}"></script><script defer src="../assets/course.js?v=${assetVersion}"></script><script defer src="../assets/reading-progress.js?v=${assetVersion}"></script></head>
<body data-course-slug="${escapeHtml(course.slug)}"><div class="course-shell"><div class="lesson-page-grid">${chapterNavHtml(lesson)}<div class="lesson-page-main">${topbar("..")}<section class="lesson-header"><div class="eyebrow">${escapeHtml(lessonLabel(lesson))} · ${escapeHtml(parsed.time)}</div><h1>${escapeHtml(lesson.title)}</h1><p class="lesson-summary">${escapeHtml(parsed.summary)}</p><a class="source-link" href="../markdown/${lesson.markdown.split("/").at(-1)}">查看 Markdown 版本</a></section><div class="lesson-layout"><main class="lesson-content">${parsed.html}${lessonNavigation(lesson)}</main>${tocHtml(parsed.toc)}</div></div></div><footer class="site-footer">${escapeHtml(course.title)} · ${publicationLabel}</footer></div></body></html>`;
  writeFileSync(join(courseRoot, lesson.href), html);
  copyFileSync(source, join(markdownRoot, lesson.markdown.split("/").at(-1)));
  return markdown;
}

// CHANGED: group chapters by module prefix and insert module headings
function renderIndex() {
  const availableCount = course.lessons.filter((item) => item.status === "available").length;
  const defaultModules = [
    { prefix: "FE-L", title: "模块一：前端语言及标准库基础", subtitle: "JavaScript、TypeScript 与 Web 标准" },
    { prefix: "FE-W", title: "模块二：Web 前端开发", subtitle: "三类 FBS 前端工程实战" },
    { prefix: "FE-A", title: "模块三：Web 前端进阶", subtitle: "微前端、诊断与开发交接" },
    { prefix: "BE-L", title: "模块四：后端语言及标准库基础", subtitle: "Go 语言与标准库" },
    { prefix: "BE-W", title: "模块五：Web 后端开发", subtitle: "三类 FBS 后端工程实战" },
    { prefix: "BE-A", title: "模块六：Web 后端进阶", subtitle: "任务、消息、缓存与可靠性" },
  ];
  const modules = course.modules?.length
    ? course.modules
    : course.lessons.some((lesson) => lesson.code)
      ? defaultModules
      : [...new Set(course.lessons.map((lesson) => lesson.module).filter(Boolean))]
          .map((title) => ({ title, subtitle: "" }));
  if (modules.length === 0) {
    modules.push({
      title: "课程章节",
      subtitle: course.description || "",
      chapterNumbers: course.lessons.map((lesson) => lesson.number),
    });
  }
  const groupedHtml = [];
  for (const mod of modules) {
    const modLessons = course.lessons.filter((l) => (
      mod.chapterNumbers?.includes(l.number)
      || (mod.prefix && l.code?.startsWith(mod.prefix))
      || (!mod.chapterNumbers && !mod.prefix && l.module === mod.title)
    ));
    if (modLessons.length === 0) continue;
    const cards = modLessons.map((lesson) => {
      const content = `<small>${escapeHtml(lessonLabel(lesson))} · ${escapeHtml(lesson.time)}</small><h3>${escapeHtml(lesson.title)}</h3><p>${escapeHtml(lesson.summary)}</p><span class="state">${lesson.status === "available" ? "开始阅读 →" : "后续批次"}</span>`;
      return lesson.status === "available"
        ? `<a class="chapter-card available" href="./${lesson.href}">${content}</a>`
        : `<article class="chapter-card planned">${content}</article>`;
    }).join("");
    groupedHtml.push(
      `<div class="module-section"><div class="module-heading"><h2>${escapeHtml(mod.title)}</h2><p>${escapeHtml(mod.subtitle)}</p></div><section class="chapter-grid">${cards}</section></div>`
    );
  }
  const allCardsHtml = groupedHtml.join("");
  const progress = `${availableCount / course.lessons.length * 100}%`;
  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="${escapeHtml(course.description)}"><title>${escapeHtml(course.title)} | AI Course Studio</title><script src="./assets/theme-switcher.js?v=${assetVersion}"></script><link rel="stylesheet" href="./assets/course.css?v=${assetVersion}"></head>
<body><div class="site-shell"><header class="topbar"><a class="brand" href="./index.html">${escapeHtml(course.title)}</a><nav><a href="./index.html">课程目录</a><a href="./reference/glossary.html">术语表</a></nav></header><section class="course-hero"><div class="eyebrow">${escapeHtml(course.kicker || "工程 Landing 课程")}</div><h1>${escapeHtml(course.title)}</h1><p class="lead">${escapeHtml(course.description)}</p><div class="meta-row"><span class="pill">${course.lessons.length} 章</span><span class="pill">${escapeHtml(course.duration)}</span><span class="pill">${escapeHtml(course.audience || "研发工程师")}</span><span class="pill">Markdown + 静态 HTML</span></div></section><section class="progress-panel"><div><strong>${availableCount} / ${course.lessons.length}</strong><span>当前开放章节</span></div><div><div class="progress-track" style="--progress:${progress}"><span></span></div><p>${escapeHtml(course.progressNote || `当前开放 ${availableCount} 章；后续章节在人工审核后继续。`)}</p></div></section><div class="section-heading"><div><h2>课程目录</h2><p>${escapeHtml(course.catalogIntro || "从真实仓库链路出发，逐章完成可验证的开发任务。")}</p></div></div>${allCardsHtml}<footer class="site-footer">${escapeHtml(course.title)} · ${publicationLabel}</footer></div></body></html>`;
  writeFileSync(join(courseRoot, "index.html"), html);
}

function renderGlossary() {
  const source = join(referenceRoot, "glossary.md");
  const lines = readFileSync(source, "utf8").split(/\r?\n/);
  const title = lines.find((line) => /^#\s+/.test(line))?.replace(/^#\s+/, "") || "术语表";
  const body = renderBlocks(lines.filter((line) => !/^#\s+/.test(line)).join("\n"));
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)} | ${escapeHtml(course.title)}</title><script src="../assets/theme-switcher.js?v=${assetVersion}"></script><link rel="stylesheet" href="../assets/course.css?v=${assetVersion}"><script defer src="../assets/course.js?v=${assetVersion}"></script><script defer src="../assets/reading-progress.js?v=${assetVersion}"></script></head><body><div class="course-shell">${topbar("..")}<section class="lesson-header"><div class="eyebrow">Reference</div><h1>${escapeHtml(title)}</h1><p class="lesson-summary">快速查阅课程中的核心术语、统计口径与使用边界。</p></section><div class="lesson-layout"><main class="lesson-content">${body.html}</main>${tocHtml(body.toc)}</div><footer class="site-footer">${escapeHtml(course.title)}</footer></div></body></html>`;
  writeFileSync(join(referenceRoot, "glossary.html"), html);
}

function validateDisclosure(files) {
  for (const file of files) {
    const content = readFileSync(file, "utf8");
    const findings = disclosureFindings(content);
    if (findings.length) {
      const details = findings
        .map((finding) => `${finding.label}（第 ${finding.line} 行：${finding.excerpt}）`)
        .join("、");
      throw new Error(`${relative(root, file)} 泄露学生不可见信息: ${details}`);
    }
  }
}

function validateLocalLinks(files, selectedNumbers = null) {
  const failures = [];
  for (const file of files) {
    const content = readFileSync(file, "utf8");
    for (const match of content.matchAll(/(?:href|src)="([^"]+)"/g)) {
      const target = match[1];
      if (/^(https?:|mailto:|#|data:)/.test(target)) continue;
      let resolved = resolve(dirname(file), decodeURIComponent(target.split(/[?#]/)[0]));
      if (existsSync(resolved) && statSync(resolved).isDirectory()) resolved = join(resolved, "index.html");
      if (!existsSync(resolved)) failures.push(`${relative(root, file)} -> ${target}`);
    }
  }
  const scopedFailures = selectedNumbers
    ? failures.filter((failure) => {
        const target = failure.split(" -> ")[1] || "";
        const match = target.match(/lessons\/(\d+)-/);
        return match ? selectedNumbers.has(Number(match[1])) : false;
      })
    : failures;
  if (scopedFailures.length) throw new Error(`本地链接无效:\n${scopedFailures.join("\n")}`);
}

mkdirSync(markdownRoot, { recursive: true });
const templateAssetsRoot = join(root, "courses", "high-quality-ai-code-review", "assets");
const targetAssetsRoot = join(courseRoot, "assets");
mkdirSync(targetAssetsRoot, { recursive: true });
for (const assetName of ["course.css", "course.js", "theme-switcher.js", "reading-progress.js"]) {
  copyFileSync(join(templateAssetsRoot, assetName), join(targetAssetsRoot, assetName));
}
if (course.mark) {
  const targetCss = join(targetAssetsRoot, "course.css");
  let themedCss = readFileSync(targetCss, "utf8").replace('--course-mark: "AICR"', `--course-mark: "${course.mark}"`);
  if (course.compactLessonTitles) {
    themedCss += '\nbody { overflow-x: hidden; }\n.lesson-header h1 { font-size: clamp(2.4rem, 4.6vw, 4rem); max-width: 20ch; }\n.lesson-layout, .lesson-content { min-width: 0; }\n.diagram-card { max-width: 100%; overflow-x: auto; }\n.lesson-content :not(pre) > code { overflow-wrap: anywhere; word-break: break-word; }\n.lesson-page-main { width: 100%; max-width: 1400px; min-width: 0; }\n.lesson-page-grid { display: grid; grid-template-columns: minmax(0, 1fr); width: 100%; }\n.course-shell:has(.chapter-nav) .lesson-page-main { max-width: calc(100vw - 390px); }\n.course-shell:has(.chapter-nav.is-collapsed) .lesson-page-main { max-width: calc(100vw - 172px); }\n.lesson-header h1 { font-size: clamp(2rem, 4vw, 4rem); overflow-wrap: anywhere; }\n.lesson-layout, .lesson-content { min-width: 0; }\n@media (max-width: 1240px) { .course-shell:has(.chapter-nav) .lesson-page-main, .course-shell:has(.chapter-nav.is-collapsed) .lesson-page-main { max-width: calc(100vw - 92px); } }\n@media (max-width: 900px) { .lesson-layout { grid-template-columns: minmax(0, 1fr); } .toc { position: static; } }\n@media (max-width: 1240px) { .course-shell:has(.chapter-nav), .course-shell:has(.chapter-nav.is-collapsed) { padding-left: 20px; } }\n';
  }
  themedCss += "\n/* Reading progress */\n.chapter-nav-list a.is-read { background: color-mix(in srgb, var(--accent) 8%, var(--surface)); border-left: 3px solid color-mix(in srgb, var(--accent) 40%, transparent); padding-left: 5px; }\n.chapter-nav-list a.is-read .chapter-nav-title { color: var(--muted-strong); }\n.chapter-nav-list a.is-read:hover { background: color-mix(in srgb, var(--accent) 14%, var(--surface-raised)); }\n.read-badge { color: var(--accent); font-weight: 600; margin-left: 2px; }\n";
  writeFileSync(targetCss, themedCss);
}
const available = course.lessons.filter((item) => (
  item.status === "available"
  && (!selectedChapterNumbers || selectedChapterNumbers.has(Number(item.number)))
));
const exported = available.map((lesson) => renderLesson(lesson));

function renderOutlineLesson(lesson) {
  const source = join(courseRoot, lesson.markdown);
  if (!existsSync(source)) return;
  const markdown = readFileSync(source, "utf8");
  const parsed = parseLesson(markdown, relative(root, source));
  const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="${escapeHtml(parsed.summary)}"><title>${escapeHtml(lesson.title)} | ${escapeHtml(course.title)}</title><script src="../assets/theme-switcher.js?v=${assetVersion}"></script><link rel="stylesheet" href="../assets/course.css?v=${assetVersion}"></head>
<body><div class="course-shell"><div class="lesson-page-main">${topbar("..")}<section class="lesson-header"><div class="eyebrow">${escapeHtml(lessonLabel(lesson))} · 后续批次</div><h1>${escapeHtml(lesson.title)}</h1><p class="lesson-summary">${escapeHtml(parsed.summary)}</p></section><div class="lesson-layout"><main class="lesson-content">${parsed.html}</main>${tocHtml(parsed.toc)}</div></div></div><footer class="site-footer">${escapeHtml(course.title)} · ${publicationLabel}</footer></div></body></html>`;
  writeFileSync(join(courseRoot, lesson.href), html);
}

const outlines = selectedChapterNumbers
  ? []
  : course.lessons.filter((item) => item.status === "outline");
for (const lesson of outlines) renderOutlineLesson(lesson);
if (!selectedChapterNumbers) {
  renderIndex();
  renderGlossary();
}
const lastAvailable = String(available.at(-1)?.number || 0).padStart(2, "0");
writeFileSync(join(markdownRoot, `course-01-${lastAvailable}.md`), exported.join("\n\n---\n\n"));

const generated = selectedChapterNumbers
  ? available.map((lesson) => join(courseRoot, lesson.href))
  : [
      join(courseRoot, "index.html"),
      join(referenceRoot, "glossary.html"),
      ...available.map((lesson) => join(courseRoot, lesson.href)),
      ...outlines.map((lesson) => join(courseRoot, lesson.href)),
    ];
const studentSources = [
  ...available.map((lesson) => join(courseRoot, lesson.markdown)),
  ...(selectedChapterNumbers ? [] : [join(referenceRoot, "glossary.md")]),
];
validateDisclosure([...studentSources, ...generated]);
validateLocalLinks(generated, selectedChapterNumbers);
console.log(`Generated ${course.title}: ${available.length} lessons${selectedChapterNumbers ? " (batch scope)" : ""}, ${course.lessons.length} chapter cards, 1 glossary, Markdown exports.`);
