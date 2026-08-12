const DISCLOSURE_RULES = [
  // “你提供的是 git log 输出”这类句子是学生练习中的正常对话。
  // 只有课程生产侧把用户提交的资料、内容或资源带入学生页面时才违规。
  ["你提供的材料", /(?:基于|根据|来自)?你提供的(?:资料|材料|内容|文档|教程|资源)/],
  ["内部材料", /内部材料/],
  // “模型蒸馏”是公开技术术语。只有描述内部生产来源时才属于泄露。
  ["蒸馏来源", /(?:内容|资料|材料)?蒸馏(?:来源|自|材料)/],
  ["样章流程", /样章(?:状态|验收|确认|生成)/],
  ["内部质检", /rubric\s*(?:得分|分数|报告|质检)|质检报告/i],
  ["Workspace 路径", /workspace\//],
  ["内部来源标记", /CLAIM-SOURCE/],
  ["等待确认", /等待(?:用户)?确认/],
  ["本机路径", /Users\/qi\.qiao/],
];

function lineAt(content, offset) {
  return content.slice(0, offset).split(/\r?\n/).length;
}

function excerptAt(content, offset, length) {
  const start = Math.max(0, offset - 36);
  const end = Math.min(content.length, offset + length + 72);
  return content.slice(start, end).replace(/\s+/g, " ").trim();
}

export function disclosureFindings(content) {
  return DISCLOSURE_RULES.flatMap(([label, pattern]) => {
    const match = pattern.exec(content);
    if (!match || match.index === undefined) return [];
    return [{
      label,
      line: lineAt(content, match.index),
      excerpt: excerptAt(content, match.index, match[0].length),
    }];
  });
}

export function disclosureViolations(content) {
  return disclosureFindings(content).map((finding) => finding.label);
}
