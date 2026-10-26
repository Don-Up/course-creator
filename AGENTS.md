# AGENTS.md

## 项目定位

本仓库是 AI Course Studio 训练营的教学脚手架。它保留 React/Vite 与
FastAPI 的最小运行链路，供学员按 `implementation-guide-20-lessons/` 逐阶段
实现课程生成 Agent。当前代码不是完整 Demo，不应假设 Agent 运行时已经存在。

## 目录职责

- `apps/web/`：React + TypeScript 前端。前端只通过 REST API 读取后端数据。
- `apps/api/`：FastAPI 后端。当前仅暴露健康检查与课程列表。
- `courses/`：静态示例课程；`courses/catalog.json` 是示例课程列表的事实源。
- `.agents/skills/`：版本化的领域与工程规则，必须整体保留。
- `implementation-guide-20-lessons/`：训练营分阶段实施指引。
- `assets/aiagent/`：存放当前项目的 PRD 和 FE-TD 和 BE-TD，根据任务类型按需读取。

## 分阶段约束

- 未进入相应阶段前，不得提前加入 LLM Provider、Fake Provider、Run、Artifact、
  数据库、LangGraph、Worker、队列、质量闭环或自动发布。
- 七阶段产品契约固定为：`intake`、`mission`、`blueprint`、`batch_plan`、
  `generation`、`quality`、`release`。
- `release` 必须保留人工决策权；模型和代码不得静默替代该决定。
- 示例课程用于观察发布结果，不代表脚手架已经能够生成或编辑课程。

## 代码规范

- 前端使用 React + TypeScript。API 契约变更必须同步更新前端类型和测试。
- 后端使用 FastAPI + Pydantic；路由按资源拆分，公开响应使用明确的返回类型或
  `response_model`。
- Python 使用 Python 3.12+（3.12 / 3.13 / 3.14 均可）、Ruff，单行最大 92 字符。
- 使用 `apply_patch` 修改源码与文档；不要覆盖或回滚已有用户改动。
- 输入路径必须规范化并限制在允许的课程目录内；初始脚手架不提供文件写入 API。
- 优先使用标准库和已有依赖。新依赖必须对应当前阶段的明确需求。
- 不提交 `.venv/`、`node_modules/`、`.course-agent/`、缓存、构建目录或 `.env`。

## Skill 适用范围

- FastAPI 代码遵循 `.agents/skills/fastapi/SKILL.md`。
- 课程生产、课程规划和质量审校遵循
  `.agents/skills/teach-generator/SKILL.md`。
- 中文学生可见正文遵循 `.agents/skills/humanizer-zh/SKILL.md`。

## 验证

涉及前端时运行：

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

涉及后端时运行：

```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests
```

变更启动或接口行为后，额外验证：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/courses
```
