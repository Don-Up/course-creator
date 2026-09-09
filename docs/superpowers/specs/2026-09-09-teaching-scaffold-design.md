# AI Course Studio 教学薄脚手架改造设计

## 目标

将当前完整的 AI Course Studio Demo 改造成训练营学员的起始分支。学员无需先搭建前后端工程，即可从第 00 阶和第 01 阶开始，按照 `implementation-guide-20-lessons/` 逐步实现完整的课程生成 Agent。

脚手架保留一个真实的 React + FastAPI 请求链路和一门可浏览的已发布课程，删除所有可执行的 AI Agent 业务实现，避免把后续阶段的答案预置给学员。

## 保留内容

- `.agents/skills/` 下的全部 Skill 文件。
- `implementation-guide-20-lessons/` 下的阶段化实现指引。
- React + Vite 前端工程和 FastAPI 后端工程。
- `GET /api/health` 健康检查接口。
- `GET /api/courses` 课程列表接口。
- 根路由课程列表页、`/workflow` 工作流蓝图页和 `/new` 简介占位页。
- `courses/advanced-learning-of-obsidian/` 的已发布静态课程页面、课程资源和精简元数据。
- `courses/catalog.json`，作为示例课程列表的唯一事实源。
- 教学参考材料 `assets/aiagent/` 与 `course-learning-guide.md`。这些材料不参与运行时，也不作为脚手架的当前实现说明。

## 删除内容

- 后端的 Agent、Provider、LangGraph、SQLite、Worker、运行命令、可观测性、质量闭环、课程编辑和课程生产实现。
- 后端中与这些能力绑定的 Schema、配置、依赖和测试。
- 前端的 Run 工作台、课程编辑器、Provider 设置、模型配置、Agent 请求类型和 API 调用。
- 前端中只服务于完整 Demo 的组件、特性目录和样式。
- 示例课程中的 `workspace/`、`quality/`、`markdown/` 等 Agent 生产过程和运行证据。
- 示例课程元数据中的 Run、审批和质量相关字段。

## 最小运行架构

`bash scripts/start-agent.sh` 只启动 Uvicorn 和 Vite，不要求 `.env`、模型凭据或 Worker。

浏览器根页面请求：

1. `GET /api/health`，确认 FastAPI 可用。
2. `GET /api/courses`，读取 `courses/catalog.json` 并显示示例课程。

课程卡片链接到 FastAPI 在受限示例课程根目录内提供的静态页面。由此形成浏览器、React、FastAPI 和仓库内课程产物之间的真实最小链路。

`/workflow` 只渲染固定的七阶段蓝图：

`intake -> mission -> blueprint -> batch_plan -> generation -> quality -> release`

该页面明确这是待学员逐步实现的产品契约，不提供 Run、模型调用或状态机。

`/new` 只说明课程创建将在阶段 01 中实现，不提交表单或写入数据。

## 模块边界

后端保留少量独立模块：

- `app/main.py`：应用装配、CORS 和静态示例课程暴露。
- `app/api/system_routes.py`：健康检查。
- `app/api/course_routes.py`：只读课程列表。
- 课程目录读取辅助模块：读取并校验课程目录和 `catalog.json`。

前端保留：

- 应用入口和路由装配。
- 基础布局。
- 课程列表页。
- 工作流蓝图页。
- 新建课程占位页。
- 用于上述页面的最小 API 客户端、类型与样式。

## 依赖策略

Python 仅保留 FastAPI、Pydantic、Uvicorn、Pytest 和 Ruff 所需依赖。移除 LangChain、LangGraph、SQLite checkpoint、HTTP 客户端和设置管理依赖。

前端仅保留 React、React Router、Vite、TypeScript 和当前页面实际使用的图标依赖。移除 React Query、动画、流程图、Markdown、代码高亮和其他完整 Demo 专用依赖。

不为了未来阶段添加接口、数据表、抽象类、假 Provider 或环境变量。后续阶段按实现指引自行引入。

## 错误处理与安全

- 前端在 API 请求失败时展示真实错误，不提供静态兜底数据。
- 课程列表无法读取时由 API 返回受控错误或空列表。
- 静态课程文件只能从预设课程根目录读取；路径必须被规范化并限制在该目录内。
- 初始脚手架不提供任何文件写入接口。

## 文档

`README.md` 将说明：

- 当前分支是教学起点而不是完整 Demo。
- 已实现与未实现的能力边界。
- 无模型配置的启动与验证方法。
- 课程示例和两条 API 的用途。
- 从阶段 00 到阶段 07 使用实现指引逐步恢复完整系统的学习路径。

`AGENTS.md` 将说明：

- 目录职责和 API 契约同步要求。
- React/TypeScript、FastAPI/Pydantic、Ruff、Pytest 和 Vite 的项目规范。
- 路径安全、依赖最小化和不提交本地生成文件的要求。
- 每个阶段只实现该阶段目标，避免提前引入后续 Agent 能力。
- `.agents/skills/` 在课程生产、中文文本和 FastAPI 工作中的适用边界。

最终还将提供一份技术实施文档。该文档以完整 Demo 为基线，记录模块级
保留与删除映射、目标目录结构、最小 API 契约、依赖裁剪、迁移顺序和实际
验证证据，供训练营维护者理解并复现本次脚手架改造。它不包含可直接复用的
Agent 实现代码。

## 验收

1. 不配置模型或 `.env` 即可运行 `bash scripts/start-agent.sh`。
2. `GET /api/health` 返回成功。
3. `GET /api/courses` 返回预设示例课程。
4. 首页显示课程卡片并能打开静态课程。
5. `/workflow` 显示七阶段蓝图，`/new` 显示简介占位内容。
6. 后端测试覆盖健康检查、课程列表和静态课程入口。
7. 前端通过类型检查和生产构建。
8. 仓库不包含可执行的 Agent、Provider、Run、Worker、SQLite、LangGraph 或质量闭环实现。
9. 技术实施文档完整说明由完整 Demo 到教学薄脚手架的改造决策与验证证据。

## 非目标

- 不实现课程创建、课程详情编辑、章节编辑或课程构建工具。
- 不实现 LLM Provider、Fake Provider、Run、Artifact、数据库、持久化、队列、Worker、LangGraph 或质量系统。
- 不修改 `.agents/skills/` 和阶段化实现指引的教学内容。
- 不把教学参考文档当作运行时依赖或当前脚手架能力。
