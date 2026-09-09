# AI Course Studio 训练营脚手架

这是 AI Course Studio 训练营的起始分支，不是完整的课程生成 Agent。

你已经拥有可启动的 React + Vite 前端、FastAPI 后端、一条真实的
`浏览器 -> /api/courses -> courses/catalog.json` 请求链路，以及一门可浏览的
已发布课程示例。课程创建、模型调用、Run、Workflow 执行、持久化、质量闭环和
发布控制均尚未实现，它们正是后续训练要亲手完成的部分。

## 从哪里开始

按 [implementation-guide-20-lessons](implementation-guide-20-lessons/README.md)
渐进实现完整项目：

1. 阶段 00：读取 `.agents/skills/`，画出七阶段产品契约。
2. 阶段 01：实现第一次可观察的七阶段 Happy Path。
3. 阶段 02 至 07：逐步加入持久化、角色与 Artifact、受控 Graph、质量闭环、
   可恢复执行和交付治理。

每个阶段都提供规划、实现、排障提示词、人工 Review 清单和验收步骤。不要跳过
当前阶段直接复制终态能力；每一层限制都会成为下一阶段要解决的问题。

## 当前脚手架

- `apps/web/`：React + TypeScript + Vite。保留课程列表、工作流蓝图和新建课程占位页。
- `apps/api/`：FastAPI。只提供 `GET /api/health` 与 `GET /api/courses`。
- `courses/`：一门已发布的静态课程示例及其目录。
- `.agents/skills/`：训练中需要使用的 `teach-generator`、`humanizer-zh` 和 `fastapi` 规则。
- `implementation-guide-20-lessons/`：从薄脚手架逐步完成完整系统的实施指引。

## 启动

前置条件：

- Node.js 20+
- Python 3.12

运行：

```bash
bash scripts/start-agent.sh
```

首次启动会创建 `apps/api/.venv` 并安装后端依赖；前端依赖缺失时会自动安装。
不需要配置 `.env`、模型密钥或本地 Gateway。

启动后访问：

- 前端：`http://127.0.0.1:5173`
- API 文档：`http://127.0.0.1:8000/docs`

首页应显示一门示例课程。打开它可以观察课程生成完成后的静态发布形态；这不是
当前脚手架具备的生成能力。

## API 验证

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/courses
```

预期健康检查返回 `status: "ok"`，课程列表返回
`advanced-learning-of-obsidian` 示例课程。

## 开发验证

```bash
apps/api/.venv/bin/python -m pytest apps/api/tests
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

## 不在当前阶段的能力

当前分支刻意不包含：

- 课程创建、编辑、构建和质量检查
- LLM 或 Fake Provider
- Course Run、Artifact、数据库和运行历史
- LangGraph、Worker、队列、恢复和人工审批

请以每个实施阶段的目标为边界，一步一步把这些能力加回来。
