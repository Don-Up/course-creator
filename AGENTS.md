# AGENTS.md

## 项目定位

本仓库是 AI 课程生成 Agent 训练营项目。目标是开发和理解一个本地优先的课程生产系统，而不是直接手工编写某一门课程。系统由 React/Vite 前端、FastAPI/LangGraph 后端和本地 SQLite 运行数据组成，课程产物保存在 `courses/<course-slug>/`。

## 任务边界

- 产品开发：涉及 `apps/web/`、`apps/api/`、工作流、Provider、数据库、构建脚本或产品文档时，按软件工程任务处理。
- 课程生产或课程内容编辑：涉及课程规划、章节生成、质量审校时，遵循 `.agents/skills/teach-generator/SKILL.md`；中文学生可见正文还要遵循 `.agents/skills/humanizer-zh/SKILL.md`。
- FastAPI 代码：遵循 `.agents/skills/fastapi/SKILL.md` 的 Python 编码规范。

## 架构与数据边界

- 前端位于 `apps/web/`，通过 REST API 访问后端；API 契约变更必须同步更新前端类型与测试。
- 后端位于 `apps/api/`。运行状态、事件、人工中断与模型 artifact 写入根目录 `.course-agent/` 中的 SQLite 文件。
- 课程正文 Markdown 位于 `courses/<slug>/lessons/`，是事实源；HTML 是由 `scripts/build-static-course.mjs` 生成的发布产物，不能直接手改。
- 课程 `workspace/` 是可审阅的生产上下文；所有文件读写必须限制在目标课程目录，防止路径穿越，并使用安全的原子替换策略。
- 本仓内置唯一课程样例为 `courses/advanced-learning-of-obsidian/`。新课程通过产品界面创建，不应复制无关课程或历史运行数据。

## 工作流约束

标准节点顺序：`intake` → `mission` → `blueprint` → `batch_plan` → `generation` → `quality` → `release`。

- 新建课程产物必须属于当前 Run，不能伪装成从本地恢复的数据。
- 节点开始、完成、等待人工确认与失败必须记录事件；模型和工具结果必须写入 artifact。
- 人工确认支持批准、要求修改与停止；连续三轮同类 blocker 后转人工审核。
- 课程质量和重建使用 `teach-generator` 提供的规则与校验脚本。

## 开发规范

- 使用 `apply_patch` 修改源码与文档；不覆盖或回滚用户已有改动。
- 不提交 `.venv/`、`node_modules/`、`.course-agent/`、缓存、构建目录或 `.env` 密钥文件。
- 变更后运行受影响范围的验证：前端至少执行 `npm --prefix apps/web run build`，后端执行对应 `pytest`，课程结构变更执行课程校验。
- Provider 能力存在差异；模型调用不能假设每个 Provider 都支持相同的 `tool_choice`、thinking mode 或结构化输出参数。
- 长任务不能阻塞 API 请求；由 Worker 在后台运行，前端通过轮询或事件展示进度。

## 启动与验证

优先使用 `bash scripts/start-agent.sh`。该脚本会创建 `apps/api/.venv`、安装依赖并同时启动 API、Worker 和前端。首次使用前将 `apps/api/.env.example` 复制为 `apps/api/.env`，再配置本地 Codex Gateway 或 `DEEPSEEK_API_KEY`。

常用命令：

```bash
npm --prefix apps/web run build
apps/api/.venv/bin/python -m pytest apps/api/tests
npm run test:contract
node .agents/skills/teach-generator/scripts/validate-course.mjs courses/advanced-learning-of-obsidian
```
