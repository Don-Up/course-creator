# 教学薄脚手架技术实施文档

## 1. 文档目的

本文记录如何把 AI Course Studio 的完整 Demo 收敛为训练营学员可直接开工的
教学薄脚手架。它面向课程维护者与助教，说明本次改造的边界、文件映射、依赖
裁剪、运行方式与验证证据。

它不提供可直接恢复完整 Agent 的实现代码。学员应按
`implementation-guide-20-lessons/` 的阶段目标自行完成后续能力。

## 2. 改造原则

完整 Demo 的职责是展示一个可运行、可恢复、可观察的课程生产系统；脚手架的
职责是为学员保留工程外壳和第一条真实前后端链路。

本次改造遵循以下规则：

1. 保留工程基础，不保留业务答案。
2. 保留一门发布态课程，不保留其 Agent 运行过程。
3. 保留七阶段名称与职责说明，不保留 Workflow 执行。
4. 保留只读 API 链路，不保留会写文件、调用模型或创建运行历史的接口。
5. 不要求模型配置、`.env`、数据库或后台 Worker 才能启动。

## 3. 完整 Demo 与脚手架映射

| 完整 Demo 区域 | 完整职责 | 脚手架处理 | 原因 |
| --- | --- | --- | --- |
| `apps/api/app/agents/` | 角色定义、模型调用、Fake Runtime | 删除 | 属于阶段 01 之后的 Agent 实现 |
| `apps/api/app/providers/`、`provider.py` | Gateway/DeepSeek Provider | 删除 | 脚手架不调用模型 |
| `apps/api/app/workflow/` | LangGraph、节点、命令、恢复与审批 | 删除 | 七阶段目前仅是教学契约 |
| `apps/api/app/db.py`、`artifact_service.py`、`observability/` | SQLite、Artifact、追踪与预算 | 删除 | 持久化与可观测性由后续阶段引入 |
| `apps/api/app/worker.py` | 长任务后台执行 | 删除 | 当前无长任务 |
| `apps/api/app/courses/`、`course_service.py` | 创建、编辑、构建、质量与工作区操作 | 删除 | 当前课程为只读示例 |
| `apps/api/app/main.py` | Demo 应用装配 | 重建 | 只装配 CORS、两条 API 和静态课程 |
| `apps/api/app/catalog.py` | 无 | 新增 | 读取并验证 `courses/catalog.json` |
| `apps/api/app/api/system_routes.py` | Provider 健康与配置 | 重建 | 只返回应用健康状态 |
| `apps/api/app/api/course_routes.py` | 全量课程 REST API | 重建 | 只读 `GET /api/courses` |
| `apps/web/src/features/run/` | Run 工作台与轮询 | 删除 | 当前不存在 Run |
| `apps/web/src/pages/course-pages.tsx` | 课程、编辑器、创建向导 | 删除并重建 | 只保留课程列表和创建占位 |
| `apps/web/src/pages/workflow-overview.tsx` | 运行拓扑和节点详情 | 删除并重建 | 仅展示静态七阶段蓝图 |
| `apps/web/src/api.ts` | 全量 Agent API 类型与调用 | 重建 | 只保留健康检查和课程列表类型 |
| 前端复杂样式与可视化依赖 | 完整工作台展示 | 删除 | 避免保留未实现能力的 UI |
| `courses/*/workspace/` | Mission、Blueprint、Context Pack 等过程事实 | 删除 | 属于 Agent 生产过程 |
| `courses/*/quality/` | 质量结果、修复与报告 | 删除 | 属于质量闭环答案 |
| `courses/*/markdown/`、`.agent-history/` | 生成中间产物与历史 | 删除 | 不作为发布课程必要内容 |
| `courses/*/lessons/*.md`、`*.html`、`assets/` | 课程源文与发布结果 | 保留 | 让学员观察最终交付形态 |
| `.agents/skills/` | 课程领域与工程规则 | 整体保留 | 是训练的规则来源 |
| `implementation-guide-20-lessons/` | 阶段化提示词与验收 | 整体保留 | 是学员的实施路线 |

## 4. 目标目录结构

```text
apps/
  api/
    app/
      api/
        course_routes.py
        system_routes.py
      catalog.py
      main.py
    tests/
      test_scaffold_api.py
  web/
    src/
      components/layout.tsx
      api.ts
      pages.tsx
      App.tsx
      main.tsx
      styles.css
courses/
  catalog.json
  advanced-learning-of-obsidian/
    assets/
    lessons/
    reference/
    index.html
    course.json
.agents/skills/
implementation-guide-20-lessons/
docs/
  teaching-scaffold-implementation.md
  superpowers/specs/2026-09-09-teaching-scaffold-design.md
scripts/start-agent.sh
```

## 5. 最小运行链路

### 5.1 数据源

`courses/catalog.json` 是课程列表的唯一事实源。它只保存展示所需的
`slug`、标题、描述、静态课程链接、章节数、时长和状态。

`courses/advanced-learning-of-obsidian/` 是只读示例课程。其发布态 HTML、Markdown
与资源保留，运行过程目录已经移除。

### 5.2 后端

应用由 `app/main.py` 装配：

- `GET /api/health` 返回 `{ "status": "ok", "service": "course-training-scaffold" }`。
- `GET /api/courses` 读取 `catalog.json`，通过 Pydantic 校验后返回课程列表。
- `/course-example/` 使用受限的静态目录挂载发布态示例课程。

脚手架没有写入接口，因此没有课程 slug 写入、路径拼接、模型调用或运行状态。

### 5.3 前端

根页面并发请求健康检查和课程列表，成功后显示示例课程卡片。课程卡片链接到
`/course-example/`，通过 Vite 开发代理抵达 FastAPI 的静态课程挂载。

`/workflow` 渲染固定的七阶段产品契约：

```text
intake -> mission -> blueprint -> batch_plan -> generation -> quality -> release
```

`/new` 是阶段 01 的简介占位页，不提供表单和提交动作。

## 6. 依赖与启动裁剪

### Python

保留：

- FastAPI
- Pydantic
- Uvicorn
- Pytest
- Ruff

删除：

- LangChain、LangGraph、SQLite checkpoint
- Provider 相关 HTTP 客户端和配置管理
- 所有 Agent/Worker 专用依赖

### 前端

保留：

- React
- React DOM
- React Router
- Vite
- TypeScript

删除：

- React Query
- 动画、流程图、Markdown 渲染和代码高亮依赖
- 完整运行工作台专用依赖

### 启动脚本

`scripts/start-agent.sh` 的职责是：

1. 创建本地 Python 3.12 虚拟环境并安装 API 依赖。
2. 安装缺失的前端依赖。
3. 自动避开已占用的 `8000` 和 `5173` 端口。
4. 启动 Uvicorn 与 Vite，并将实际 API 地址传给 Vite 代理。
5. 在 `Ctrl+C` 时停止本次脚本启动的两个进程。

脚本不读取 `.env`，不验证模型密钥，也不启动 Worker。

## 7. 迁移顺序

维护者从完整 Demo 创建脚手架分支时，按以下顺序操作：

1. 先确认 `.agents/skills/`、阶段指引和示例课程发布文件属于保留范围。
2. 删除后端 Agent、Workflow、Provider、数据库、Worker、质量和写操作模块。
3. 删除与这些模块绑定的测试、环境配置和根目录 Agent 专用脚本。
4. 重建只有健康检查、课程列表和静态课程挂载的 FastAPI 应用。
5. 删除前端 Run 工作台、编辑器、模型配置和全量 API 客户端。
6. 重建三条教学路由与最小样式。
7. 删除示例课程的运行过程目录，清理其元数据中的 Run/发布审批字段。
8. 更新 Vite 代理、启动脚本、依赖清单、README 与 AGENTS。
9. 用自动化测试、构建和真实 HTTP 请求验证完整链路。

此顺序的要点是：先划定要保留的教学材料与最终课程，再删除运行实现，最后才重建
最小外壳。这样不会把样例课程误当作 Agent 状态，也不会留下失效 UI。

## 8. 验证证据

改造完成后，在 2026-09-09 实际执行并通过：

```text
apps/api/.venv/bin/python -m pytest apps/api/tests
3 passed

apps/api/.venv/bin/ruff check apps/api
All checks passed

npm --prefix apps/web run typecheck
success

npm --prefix apps/web run build
success
```

真实运行验证：

```text
bash scripts/start-agent.sh
前端: http://127.0.0.1:5174
API:  http://127.0.0.1:8001/docs

GET http://127.0.0.1:5174/api/health
200 {"status":"ok","service":"course-training-scaffold"}

GET http://127.0.0.1:5174/api/courses
200，返回 advanced-learning-of-obsidian

GET http://127.0.0.1:5174/course-example/
200

GET http://127.0.0.1:5174/workflow
200

GET http://127.0.0.1:5174/new
200
```

端口不是固定值。此次使用 `5174` 和 `8001` 是因为本机的默认
`5173` 和 `8000` 已被其他服务占用，启动脚本自动选择了下一个可用端口。

## 9. 后续阶段接入点

学员不需要重新搭建工程。阶段 00 从 `.agents/skills/` 与七阶段静态工作流页开始；
阶段 01 在现有 FastAPI 与 React 路由上新增最小输入、Runner、Fake Provider 和人工
release；阶段 02 以后再逐步引入持久化、Artifact、角色、Graph、质量闭环和 Worker。

任何后续实现都应在完成当前阶段验收后再进入下一阶段，避免把完整 Demo 的复杂度
一次性重新放回脚手架。
