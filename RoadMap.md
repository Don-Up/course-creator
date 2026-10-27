# AI Course Studio 开发路线图（RoadMap）

> **从教学薄脚手架 → 可交付的课程生成 Agent**
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（推荐）
> 或 `superpowers:executing-plans` 逐个**计划**实施本文件。本文件把工作拆成
> **9 个阶段（Phase）· 70 个计划（Plan）**；**每个计划 = 一个可独立执行的开发任务**，
> 自带文件清单、接口、步骤和验收命令，可以直接交给一个没有其他上下文的执行者。
> 计划内按 "先写失败测试 → 跑一次确认失败 → 实现 → 跑一次确认通过 → 提交" 的节奏执行。
>
> 当前仓库：`pratice/project-create-course-ai-agent`（教学脚手架，15 次提交；
> 脚手架本身由 `48b9828 feat: create training scaffold` 从目标版裁剪而来）
> 目标基准：`project/project-create-course-ai-agent`（`main` @ `9628ff2`，完整可交付版本）
>
> **Goal:** 在不推翻现有工程外壳的前提下，把薄脚手架逐层加厚成一套完整的、
> 本地优先、可恢复、可审计的课程生产 Agent——后端 74 个 Python 文件 / 10,189 行，
> 前端 33 个源文件 / 6,790 行，160 个后端测试。
>
> **Architecture:** 三层叠加，不做替换。七阶段产品契约
> （`intake → mission → blueprint → batch_plan → generation → quality → release`）
> 从第一行代码起就是固定的；每一层只增加"事实存放位置 + 控制权归属 + 可观察边界"。
>
> **Tech Stack:** Python 3.12 · FastAPI 0.139.2 · Pydantic 2.13.4 · LangGraph 1.2.9
> · langgraph-checkpoint-sqlite 3.1.0 · LangChain 1.3.14 · SQLite（标准库 `sqlite3`）
> · React 19.2.0 · TypeScript 5.9.3 · Vite 7.3.1 · TanStack Query 5.101.2 ·
> `@xyflow/react` 12 · mermaid 11 · react-markdown 10
>
> **Spec:** [`assets/aiagent/PRD.md`](assets/aiagent/PRD.md) ·
> [`assets/aiagent/BE-TD.md`](assets/aiagent/BE-TD.md) ·
> [`assets/aiagent/FE-TD.md`](assets/aiagent/FE-TD.md)
>
> **学习指引（已存在，不必重写）:** [`implementation-guide-20-lessons/`](implementation-guide-20-lessons/README.md)
> 阶段 00–07 的教学法、提示词与验收关卡由它负责。
> **本文件负责的是"工程侧要建哪些文件、接口长什么样、什么算做完"。**

---

## 0. 如何使用本文件

| 你要做的事 | 读哪里 |
| --- | --- |
| 了解"现在有什么、还差什么" | §1 现状对比 |
| 看整体排期（9 个阶段） | §3.0.2 全部计划索引 |
| **只领一个任务去做** | §3 里对应计划的 `#### Pn.k` 小节 |
| 想知道某个接口的确切签名 | §2 目标架构速览 + 各计划的「接口」段 |
| 提交前自检 | §4 全局约束 + §5 最终验收矩阵 |
| 避免踩目标版本已知的坑 | §6 目标版本已知缺陷 |

### 0.1 本文件的粒度：阶段 → 计划 → 任务

```text
阶段 Phase 0..8     = 一组共享同一套事实模型的计划（对应教学指南的一个阶段）
  └─ 计划 Plan Pn.k = 一个独立开发任务：自带 文件 / 接口 / 步骤 / 验收 命令
       └─ 步骤        = 最小可检查动作（写失败测试 → 跑失败 → 实现 → 跑通过 → 提交）
```

- **一个计划做完 = 一次独立提交 + 一条跑通的验收命令。**
- **一个计划可以交给一个完全不了解上下文的执行者**——它需要的一切决定都写在计划里。
- **阶段不能跳过；同一阶段内的计划可以并行**（前提是它们没有依赖关系，见 §3.0.2 的「依赖」列）。
- 计划编号即执行顺序：`P4.3` 必须排在 `P4.2` 之后。

### 0.2 推进顺序是强制的

每个阶段都建立在上一个阶段的事实模型之上：
阶段 1 的 Run 还在内存里，阶段 2 才把它落进 SQLite；阶段 2 的产物还没有版本，阶段 3 才引入 Artifact；
阶段 3 的调用是固定顺序，阶段 4 才把它变成可路由的状态图；阶段 5 的质量结论只是一句话，
阶段 6 才让它能挂起等待人工；阶段 6 的执行权在 API 进程里，阶段 7 才交给可恢复的 Worker。
跳过任何一个阶段，你最后会得到一个"看起来能跑但不知道内部发生了什么"的东西——
这正是 `implementation-guide-20-lessons/README.md` 开篇警告过的失败模式。

> **关于里程碑顺序的来源（重要）：**
> 目标仓库的 `main` 分支只有集成后的最终形态（`608881d feat: 完整可交付课程版本` +
> 若干文档/Skill 提交）；**逐阶段的开发历史在 feature 分支上**
> （`daotin` / `fengji-dev` / `feature-hgking-20260920` 等），
> 其真实顺序是 **01 → 02 → 04 → 05 → 06 → 07 → 03**——
> 也就是说，原作者是把"角色拆分"（阶段 03）**放在最后**做的，
> 因为那时"万能 Prompt"已经被真实调用逼出了具体痛点。
>
> **本路线图刻意不照抄那个顺序**，而是按 `implementation-guide-20-lessons/` 的
> **00 → 07 教学顺序**排列（阶段 03 在阶段 04 之前）。理由：
> 教学目标是让学员**第一次就建立正确的边界**，而不是先写出一个万能 Prompt
> 再回头重构它——那正是被这份仓库的教学材料反复警告的反模式。
> 如果你是在复现原作者的历史而不是在学这套设计，把 M3 挪到最后即可，
> 其余里程碑的依赖关系不变。

---

## 1. 现状对比

### 1.1 规模对比

| 区域 | 当前（脚手架） | 目标（完整版） | 倍数 |
| --- | ---: | ---: | ---: |
| 后端 `apps/api/app/` | 6 文件 / 101 行 | 74 文件 / 10,189 行 | ×100 |
| ├ `app/workflow/` | — | 32 文件 / 5,441 行 | 新增 |
| ├ `app/agents/` | — | 8 文件 / 1,249 行 | 新增 |
| ├ `app/courses/` | — | 8 文件 / 902 行 | 新增 |
| ├ `app/root`（main/config/db/schemas…） | 3 文件 / 78 行 | 11 文件 / 1,628 行 | ×21 |
| ├ `app/api/` | 2 文件 / 63 行 | 5 文件 / 406 行 | ×6 |
| ├ `app/providers/` + `app/observability/` + `app/tools/` | — | 10 文件 / 563 行 | 新增 |
| 后端测试 `apps/api/tests/` | 1 文件 / 24 行 / 3 测试 | 15 文件 / 3,300 行 / 160 测试 | ×53 |
| 前端 `apps/web/src/` | 6 文件 / 386 行 | 33 文件 / 6,790 行 | ×18 |
| ├ `src/features/run/` | — | 11 文件 / 2,420 行 | 新增 |
| ├ `src/styles/` | — | 11 文件 / 2,619 行 | 新增 |
| 根级脚本与契约测试 | 1 文件（`start-agent.sh`） | 8 文件 / 923 行 | ×8 |

### 1.2 已经对齐的部分（**不要重做，不要改写**）

以下内容在两个仓库中**逐字节一致**（`diff -rq` 已验证），直接沿用：

| 目录 | 状态 |
| --- | --- |
| `.agents/skills/`（teach-generator / humanizer-zh / fastapi，共 40 个文件） | ✅ 完全一致 |
| `implementation-guide-20-lessons/`（00–07 + README + templates） | ✅ 完全一致（当前多一份 `teaching-scaffold-implementation.md`） |
| `assets/aiagent/PRD.md` · `BE-TD.md` · `FE-TD.md` | ✅ 完全一致 —— 这是本路线图的规格来源 |
| `course-learning-guide.md` | ✅ 完全一致 |
| `courses/advanced-learning-of-obsidian/{lessons,reference,assets}/` + `index.html` | ✅ 完全一致 —— 9 章正文与发布态 HTML |
| `courses/advanced-learning-of-obsidian/course.json` | ⚠️ 当前已剥离 `publication` / `audience` / `modules` / `workflow_run_id` 字段，目标版保留 |
| `courses/catalog.json` | ⚠️ 仅 `href` 不同（当前 `/course-example/` → 目标 `./advanced-learning-of-obsidian/index.html`） |

### 1.3 缺失能力清单

| # | 能力 | 当前状态 | 目标状态 | 归属里程碑 |
| --- | --- | --- | --- | --- |
| 1 | 课程创建（`POST /api/courses`） | ✗ 不存在 | 建脚手架目录 + Run + intake Artifact + 入队 `START` | M1 |
| 2 | 模型调用抽象 | ✗ 不存在 | `ModelTransport` Protocol + DeepSeek + Codex Gateway + Fake | M1 / M3 |
| 3 | 七步流程执行 | ✗ 仅静态蓝图页 | LangGraph 22 节点图 + 条件边 + 8 个 `interrupt()` 审批点 | M1 / M4 |
| 4 | 持久化事实 | ✗ 不存在 | SQLite 13 张表（runs / events / artifacts / repair_tasks / commands / node_executions / trace_spans / budget…） | M2 |
| 5 | 角色与 Artifact | ✗ 不存在 | 7 个 AgentDefinition + Artifact 版本化 + 血缘边 | M3 |
| 6 | 受控工具 | ✗ 不存在 | 4 个 ToolManifest + 调用方白名单 + 路径护栏 | M3 |
| 7 | Context Pack | ✗ 不存在 | 按章组装上下文，写入 `workspace/context-packs/<batch>/chapter-NN.json` | M4 |
| 8 | 批次规划 | ✗ 不存在 | 按模块边界 + ≤4 章切批，id 形如 `m3-04-05` | M4 |
| 9 | 质量闭环 | ✗ 不存在 | 三段质量门 + RepairTask + 升级阶梯 + 回归检测 | M5 |
| 10 | 静态构建 / 确定性校验 | ✗ 不存在 | `build-static-course.mjs` / `validate-course.mjs` / `course-structure-contract.mjs` | M5 / M8 |
| 11 | 后台 Worker | ✗ 不存在 | 独立进程 + SQLite 租约队列 + 节点级幂等 | M6 |
| 12 | 人工控制 | ✗ 不存在 | approve/revise/stop/continue + SSE 事件流 | M6 |
| 13 | 可观测性 | ✗ 不存在 | Trace span 树 + Token 预算账本 | M7 |
| 14 | Run 工作台 | ✗ 不存在 | 7 步流程图 / 事件轨 / 批次矩阵 / 质量面板 / Trace 面板 | M2 → M7 |
| 15 | 课程与章节编辑 | ✗ 只读静态示例 | 乐观并发（`content_hash`）+ 快照 + Artifact 提交 | M2 / M3 |
| 16 | Provider 设置 | ✗ 不存在 | `PUT /api/settings/provider`，密钥不回落前端 | M7 |
| 17 | Workflow 拓扑 API | ✗ 静态前端常量 | `GET /api/workflow` 从可执行图导出 | M7 |

### 1.4 当前脚手架的三个"教学性谎言"（必须被替换掉）

脚手架 README 里写明的三处刻意保留，随着里程碑推进要逐一拆掉：

1. `README.md` 承诺"课程创建、模型调用、Run、Workflow 执行、持久化、质量闭环和发布控制均尚未实现" → M1–M7 逐条实现，M8 改写 README。
2. `apps/api/app/catalog.py` 是**唯一**的课程读取实现，`app/api/course_routes.py` 只有 `GET /api/courses` → M2 拆成 `app/courses/catalog.py`（文件系统扫描）+ `app/course_service.py`（门面），路由层扩展到 13 条。
3. `apps/web/src/pages.tsx` 里的 `workflowSteps` 数组是**前端硬编码**的七阶段 → M4 起由 `GET /api/workflow` 提供，`workflow-overview.tsx` 只做布局。

---

## 2. 目标架构速览

实现完成后必须成立的形状。**每个里程碑结束时，你都应能指着下面这张图说清"我完成了哪一块"。**

```
┌─ HTTP 层 ─────────────────────────────────────────────────────────────┐
│ FastAPI: 3 个 router                                                  │
│   /api/system    health · settings/provider · workflow                 │
│   /api/courses   列表·创建·详情·workspace·章节·素材·工具·runs        │
│   /api/runs      列表·详情·budget·trace·resolve·continue·stop·stream │
│   （无 response_model；Artifact 只在 GET /api/runs/{id} 内暴露）       │
└───────────────┬────────────────────────────────────────────────────────┘
                │ 只提交 Command，返回 202 / QUEUED
┌───────────────▼──────────────┐   claim lease   ┌──────────────────────┐
│ commands 表（PENDING→LEASED） │◄────────────────┤ app.worker（独立进程）│
│   kind: START/RESUME/CONTINUE│                 │  1s 轮询 · 45s 租约   │
│   /STOP · 心跳 · 取消标志     │                 └──────────┬───────────┘
└───────────────┬──────────────┘                            │
                │                                    ┌───────▼────────┐
                │                                    │ WorkflowRuntime │
                │                                    │ LangGraph 图执行│
                │                                    │ SqliteSaver     │
                │                                    └───────┬────────┘
                │            ┌───────────────────────────────┼──────────────────┐
                │            ▼                               ▼                  ▼
        ┌───────┴──────┐  ┌────────────┐  ┌────────────────────┐  ┌──────────────┐
        │ Agent Runtime│  │  ToolRuntime│  │  Quality Cycle      │  │ Observability│
        │ 7 个角色      │  │ 4 个受控工具│  │ RepairTask + 升级梯 │  │ Trace + 预算 │
        └───────┬──────┘  └──────┬─────┘  └─────────┬──────────┘  └──────────────┘
                │                │                    │
        ┌───────▼────────────────▼────────────────────▼───────────┐
        │ 事实源：courses/<slug>/                                  │
        │   workspace/  MISSION · BLUEPRINT · CONTEXT-PACKS        │
        │   lessons/    Markdown 正文（学生可见事实源）             │
        │   quality/    批次结果 · 质量快照 · 失效记录             │
        └──────────────────────────────────────────────────────────┘
```

### 2.1 必须冻结的领域契约

这些是 PRD / BE-TD / FE-TD 规定、**不允许静默改变**的部分：

| 契约 | 精确值 |
| --- | --- |
| 七阶段 id | `intake` · `mission` · `blueprint` · `batch_plan` · `generation` · `quality` · `release` |
| 审批动作 | `APPROVE` · `REVISE` · `STOP`（release 另有 `REGENERATE_SUMMARY`） |
| 审批中断类型 | `MISSION_APPROVAL` · `BLUEPRINT_APPROVAL` · `BATCH_PLAN_APPROVAL` · `BATCH_APPROVAL` · `BATCH_REVIEW_REQUIRED` · `COURSE_QUALITY_REVIEW` · `RELEASE_APPROVAL` · `COURSE_REVIEW_APPROVAL` |
| Run 状态 | `QUEUED` · `RUNNING` · `WAITING_APPROVAL` · `COMPLETED` · `FAILED` · `STOPPED` |
| Command kind | `START` · `RESUME` · `CONTINUE` · `STOP` |
| Command 终态 | `SUCCEEDED` · `FAILED` · `CANCELLED` · `WAITING_APPROVAL`（+ `RETRYABLE`） |
| Run 记录 id | `run_id == trace_id` |
| 质量门阈值 | Humanizer ≥ `45/50`；语义审校 `decision == "ready"`；有效字符 ≥ `effective_char_min`（默认 12000） |
| 返工上限 | 同类 blocker 连续 3 轮未解决 → 转人工；单任务定向尝试 ≤ 2 次；同轮发现扫描 ≤ 2 轮 |
| 批次切分 | 单批 ≤ 4 章，**不跨模块边界**；批次 id `m<批次序>-<首章>-<末章>` |
| 上下文包裁剪 | `RESOURCES.md` ≤ 48,000 字符；`COURSE-GENERATION-SPEC.md` ≤ 65,536；`NOTES.md` ≤ 32,000 |

### 2.2 七个 Agent（目标版 `app/agents/definitions.py`）

| agent id | 职责 | 输出 artifact | 工具 | 模型策略 |
| --- | --- | --- | --- | --- |
| `mission.agent` | 任务定义与增量工作区修订 | `mission` | `workspace.read` | `planning.v1` |
| `research.agent` | 资料检索计划与候选筛选 | `source_pack` | `source.search` | `planning.v1` |
| `blueprint.agent` | 模块/章节/教学路径设计 | `blueprint` | `workspace.read` | `planning.v1` |
| `writer.agent` | 学生可见章节正文写作 | `chapter_draft` | — | `writer.v1` |
| `reviewer.agent` | 教学质量、语义、连续性审校 | `quality_result` | `source.read` | `review.v1` |
| `repair.agent` | 章节问题定向修复 | `repair_plan` | — | `repair.v1` |
| `presenter.agent` | 产物用户可读摘要 | `presentation` | — | `presenter.v1` |

### 2.3 四个受控工具（目标版 `app/tools/runtime.py`）

| tool id | 允许调用方 | 幂等 | 实现 |
| --- | --- | --- | --- |
| `course.source_contract` | `workflow.generation` / `workflow.quality` / `workflow.repair` / `workflow.review` | ✅ | `course-structure-contract.mjs scan` |
| `course.build` | 同上 | ❌ | `build-static-course.mjs <slug>` |
| `course.validate` | 同上 | ✅ | `validate-course.mjs` |
| `workspace.patch` | `workflow.planning` | ❌ | `apply_workspace_patch_plan()` |

### 2.4 13 张 SQLite 表

`runs` · `run_events` · `run_artifacts` · `artifacts` · `artifact_edges` ·
`chapter_versions` · `repair_tasks` · `repair_task_attempts` · `commands` ·
`node_executions` · `trace_spans` · `budget_ledger_entries` · `budget_adjustments`

外加 LangGraph 专用的 `checkpoints.db`（与业务库分离）。全部位于 `.course-agent/`，**不入 Git**。

---

## 3. 阶段与计划（Phases & Plans）

> **编号对照**：`M0`–`M8` 与 `Phase 0`–`Phase 8` 是**同一批阶段**的两种叫法。
> §1 / §5 / §6 / §7 沿用旧的 `M` 编号（读起来短），§3 用 `Phase` + `Plan` 编号（可落到单个任务）。
> `M3` ≡ `Phase 3`（角色 / Skill / Artifact），以此类推。

### 3.0 怎么读这一节

- **阶段（Phase）** = 一组共享同一套事实模型的计划，对应 `implementation-guide-20-lessons/` 的一个教学阶段。
- **计划（Plan）** = **一个可独立执行的开发任务**。每个计划自带文件清单、接口、步骤和验收命令，
  可以直接交给一个**没有其他上下文**的 Agent 或同事独立完成、独立评审、独立提交。
- **阶段不能跳过，计划可以并行。** 同一阶段内的计划之间只有一条依赖链（见 3.0.1），
  不同阶段之间严格串行。

每个计划的完成定义只有一条：**它自己的"验收"命令必须真的跑过并通过。**

### 3.0.1 计划执行模板

每个计划都按同一节奏实施：

```text
1. 读计划里的「接口」段，确认 Consumes 的名字与上一个计划的 Produces 完全一致
2. 按「步骤」写失败测试 → 跑一次确认失败 → 实现 → 跑一次确认通过
3. 跑「验收」命令
4. 提交（一个计划一次提交，提交信息用计划标题）
5. 把真实输出填进 implementation-guide-20-lessons/templates/stage-evidence.md
```

> **铁律**：永远不要写"应该通过"。`NOT RUN` 必须写明真实原因。
> **Agent 的完成声明不是证据**，你亲手跑出来的结果才是。

### 3.0.2 全部计划索引（70 个）

| # | 计划 | 一句话产出 | 依赖 |
| --- | --- | --- | --- |
| **Phase 0 · 工程底座与契约冻结** ||||
| P0.1 | 升级并锁定 Python 依赖 | `pyproject.toml` 依赖表就位 | — |
| P0.2 | 建立 Settings 配置系统 | `app/config.py` + 路径属性可断言 | P0.1 |
| P0.3 | 提供 `.env.example` 与 Provider 配置面 | 11 项环境变量模板 | P0.2 |
| P0.4 | 建立根 `package.json` 与契约测试骨架 | `npm run test:contract` 可跑 | — |
| P0.5 | 建立 500 行规模门（脚本 + pytest 双入口） | 越界文件会让 pytest 失败 | P0.4 |
| P0.6 | 更新 `.gitignore` 与前端依赖 | 敏感目录不进 Git；9 个前端依赖到位 | P0.1 |
| **Phase 1 · 七步 Happy Path V0** ||||
| P1.1 | 定义七阶段契约常量 | `WORKFLOW_STEPS` + `STEP_ORDER` | P0.2 |
| P1.2 | 定义 Agent Protocol | 10 个方法签名（仅协议，无实现） | P1.1 |
| P1.3 | 实现 FakeProvider | 13 个输出 Schema + 确定性输出 + 可触发失败 | P1.2 |
| P1.4 | 建立路径护栏与原子写 | `_safe_course_root` / `_safe_child` | P0.2 |
| P1.5 | 实现课程脚手架创建 | 建目录 + `course.json` | P1.4 |
| P1.6 | 实现课程目录扫描与课程门面 | `list_courses()` / `get_course()` | P1.5 |
| P1.7 | 暴露 `POST /api/courses` | 201 / 409 / 422 三种结果 | P1.6 |
| P1.8 | 前端：创建向导 + 课程详情路由 | 三段表单能建课 | P1.7 |
| **Phase 2 · 持久化事实与 Run 工作台** ||||
| P2.1 | 建立 SQLite schema 与连接管理 | 13 张表建好，迁移幂等 | P0.1 |
| P2.2 | 建立 Run 仓储（落账） | Run / Event / Artifact 三类写入 | P2.1 |
| P2.3 | 建立失败事务与写入幂等 | 半截记录不会留下 | P2.2 |
| P2.4 | 建立工作区与章节乐观并发读写 | 陈旧写入 → 409 | P2.1 |
| P2.5 | 暴露 `GET /api/runs` 与完整读模型 | 刷新后仍能读到 Run | P2.2 |
| P2.6 | 前端：轮询判定 `shouldPollRun` | 终态且无活跃命令才停轮询 | P2.5 |
| P2.7 | 前端：Run 工作台最小版 | 阶段条 + 事件轨 | P2.6 |
| P2.8 | 从可执行图导出 workflow snapshot | 拓扑不再手写两份 | P2.1 |
| **Phase 3 · 角色、Skill 与 Artifact** ||||
| P3.1 | 定义 ModelPolicy 与 AgentDefinition | 5 条策略 + 7 条角色定义 | P1.2 |
| P3.2 | 实现 TeachingAgentRuntime 与操作白名单 | 越权调用被拒 | P3.1 |
| P3.3 | 实现 ToolRuntime 与调用方白名单 | 4 个受控工具 + 权限拒绝 | P3.1 |
| P3.4 | 建立 ModelTransport 协议与 DeepSeek 实现 | 可替换的传输层 | P3.1 |
| P3.5 | 建立 Codex Gateway 传输与模型发现 | 双 Provider 可切换 | P3.4 |
| P3.6 | 打包 teach-generator Skill 资产进 Prompt | Skill 原文注入而非复制 | P3.2 |
| P3.7 | 实现 Artifact 提交与血缘 | 候选不可变 + supersedes 边 | P2.1 |
| P3.8 | 补齐 Agent 输出 Schema 与协议方法 | 30 个 Pydantic 模型 | P3.1 |
| **Phase 4 · Graph、Context 与批次控制** ||||
| P4.1 | 定义 CourseAgentState | 49 字段，不含正文 | P3.8 |
| P4.2 | 实现批次切分 `_make_batches` | 不跨模块，单批 ≤ 4 章 | P4.1 |
| P4.3 | 实现 Context Pack 组装与裁剪 | 落盘 7 键 JSON | P4.2 |
| P4.4 | 实现工作区契约同步与路由判定 | 契约不符走重试分支 | P4.3 |
| P4.5 | 实现规划节点（mission / blueprint / plan） | 3 个节点 + 各自路由 | P4.4 |
| P4.6 | 实现生成节点 `generate_batch` | 单章完整质量链 | P4.5 |
| P4.7 | 实现修复与整课质量节点 | 修复队列 + 质量审校 | P4.6 |
| P4.8 | 实现发布节点与 8 个审批中断 | 人工决策点全部可挂起 | P4.7 |
| P4.9 | 装配两张可执行图 | 22 节点 + 4 节点 | P4.8 |
| **Phase 5 · 含 Humanizer 的质量闭环** ||||
| P5.1 | 质量 finding 分类与归一化 | 三类 finding 分得开 | P4.7 |
| P5.2 | RepairTask 生命周期 | 状态机 + 证据刷新 | P5.1 |
| P5.3 | 队列合并与回归检测 | 同章合并成 1 次 sweep | P5.2 |
| P5.4 | 升级阶梯 | 4 级 + 转人工 | P5.3 |
| P5.5 | 结构契约脚本（Markdown AST） | 4 个诊断码 | P0.4 |
| P5.6 | 披露契约脚本 | 9 条规则 + 误报边界 | P5.5 |
| P5.7 | 质量快照读写 | 快照是唯一权威 | P5.4 |
| P5.8 | 前端：批次矩阵与质量面板 | 三个审校面板 | P5.7 |
| **Phase 6 · 可恢复执行与人工控制** ||||
| P6.1 | 命令队列入队与幂等 | 同 `command_id` 不重复入队 | P2.1 |
| P6.2 | 租约领取与续租 | 过期可被接管 | P6.1 |
| P6.3 | 节点级幂等 claim | `claimed`/`reused`/`busy` | P6.2 |
| P6.4 | WorkflowRuntime 与检查点续跑 | 从失败点恢复 | P4.9 · P6.3 |
| P6.5 | Worker 独立进程 | 无 HTTP 端口 | P6.4 |
| P6.6 | 暴露 resolve / continue / stop / SSE | 4 条人工控制路由 | P6.4 |
| P6.7 | 启动脚本三进程 + Provider 校验 | API + Worker + Vite | P6.5 |
| P6.8 | 前端：执行面板与审批按钮矩阵 | 按钮矩阵逐条复刻 | P6.6 |
| **Phase 7 · 可观测性与交付治理** ||||
| P7.1 | Trace 上下文与 span | `trace_id == run_id` | P2.1 |
| P7.2 | 属性白名单与 Trace 投影 | 敏感属性不落库 | P7.1 |
| P7.3 | 预算账本与投影 | 超阈值只发一次事件 | P7.2 |
| P7.4 | 暴露 `GET /api/workflow` | 从可执行图导出拓扑 | P4.9 |
| P7.5 | 暴露 `PUT /api/settings/provider` | 密钥不回落前端 | P0.3 |
| P7.6 | 僵死 Run 恢复 | `RUNNING` → `FAILED` | P6.2 |
| P7.7 | 前端：Trace 与预算面板 | 两个面板 | P7.3 |
| P7.8 | 前端：编排图与样式层 | React Flow + 12 个样式文件 | P7.4 |
| **Phase 8 · 交付收敛** ||||
| P8.1 | 静态课程构建脚本（12 步） | Markdown → HTML 确定性重建 | P5.5 · P5.6 |
| P8.2 | 根级契约测试补齐 10 条 | `npm run test:contract` 全绿 | P8.1 |
| P8.3 | 补齐样例课程 `workspace/` 与 `quality/` | 可被 Review 图读取 | P2.8 |
| P8.4 | 补回 `course.json` 发布元数据 | `publication` / `modules` 等 | P8.3 |
| P8.5 | 修失效测试 + 补 `response_model` | 目标版 4 条失效测试转绿 | P2.5 |
| P8.6 | 截图与 README / AGENTS 改写 | 打开就能演示 | P8.2 · P8.4 |
| P8.7 | 全量验收与阶段证据 | §5 全部命令跑过 | P8.5 · P8.6 |

---

### Phase 0 · 工程底座与契约冻结

**阶段目标**：把依赖、目录规范、代码规模门、配置系统一次装好，让后面 8 个阶段只写业务代码。
**进入条件**：仓库是干净的教学脚手架。
**退出条件**：`pytest` 可跑、`npm run test:contract` 可跑、规模门会拦截越界文件、`Settings` 可被断言。

#### P0.1 · 升级并锁定 Python 依赖

**产出**：`apps/api/pyproject.toml` 里有一套可复现安装的依赖表。

**文件**
- Modify: `apps/api/pyproject.toml`

**接口**
- Consumes: 无
- Produces: 依赖 `fastapi==0.139.2` · `pydantic==2.13.4` · `pydantic-settings==2.13.1` · `uvicorn[standard]==0.41.0` · `httpx==0.28.1` · `langchain==1.3.14` · `langchain-deepseek==1.1.0` · `langgraph==1.2.9` · `langgraph-checkpoint-sqlite==3.1.0`；dev 组 `pytest==8.4.2` · `ruff==0.12.11`；`requires-python = ">=3.12"`；Ruff `line-length = 92` / `target-version = "py312"`

**步骤**
- [ ] 在 `pyproject.toml` 的 `[project].dependencies` 写入上面 9 个运行时依赖（**精确版本，不用 `^`**）
- [ ] `requires-python` 放宽为 `>=3.12`；`description` 改为 `"Local-first course generation agent for AI Course Studio"`
- [ ] 跑 `pip install -e "apps/api[dev]"` → 必须无解析冲突
- [ ] 跑 `python -c "import langgraph, langchain, fastapi, pydantic_settings; print('ok')"` → 打印 `ok`
- [ ] 提交：`git commit -m "chore: 锁定后端依赖版本"`

**验收**
```bash
apps/api/.venv/bin/python -c "import langgraph, langchain, fastapi, pydantic_settings; print('ok')"
apps/api/.venv/bin/ruff check apps/api        # All checks passed
```

#### P0.2 · 建立 Settings 配置系统

**产出**：一个可被测试断言的 `Settings` 类，所有路径都从它派生。

**文件**
- Create: `apps/api/app/config.py`
- Create: `apps/api/tests/test_config.py`

**接口**
- Consumes: P0.1 的 `pydantic-settings`
- Produces: `get_settings() -> Settings`（`@lru_cache`）；`Settings.repo_root` · `.courses_root` · `.data_root` · `.database_path` · `.checkpoint_path` · `.provider_preferences_path`（全部为 `Path` 属性）；`get_provider_preferences()` / `save_provider_preferences()`

**步骤**
- [ ] 写 `test_config.py::test_settings_paths_derive_from_repo_root`，断言 `settings.courses_root == settings.repo_root / "courses"`、`settings.data_root.name == ".course-agent"`
- [ ] 写 `test_config.py::test_settings_defaults_are_safe`，断言 `llm_provider == "codex_gateway"`、`llm_model == "llm-gateway--kimi-k3"`、`llm_timeout_seconds == 90`、`worker_lease_seconds == 45`
- [ ] **默认值测试必须与环境隔离**：该测试要构造 `Settings(_env_file=None)`（跳过 `apps/api/.env` 与 `.env`），并对上面 4 个键用 `monkeypatch.delenv(<键>, raising=False)` 清掉 shell 里导出的同名环境变量。原因：`_env_file=None` **只屏蔽 .env 文件**，shell 里导出的 `LLM_PROVIDER` 之类仍会盖掉默认值；少了这一步，一个开发者本地建了 `apps/api/.env` 就会让这条测试变红。
- [ ] 跑 `pytest apps/api/tests/test_config.py -v` → FAIL（`ModuleNotFoundError: app.config`）
- [ ] 实现 `app/config.py`：`class Settings(BaseSettings)`，`model_config = SettingsConfigDict(env_file=(".env", "apps/api/.env"), extra="ignore")`
- [ ] 按下方附录 P0.2.1 写入 **29 个字段**（名称 · 类型 · 默认值逐字照抄）
- [ ] 实现 6 个路径属性（全部是 `@property`，**不是**字段）：`repo_root` = `Path(__file__).resolve().parents[3]`，其余 5 个从它派生
- [ ] 按下方附录 P0.2.2 实现 `get_provider_preferences()` / `save_provider_preferences()`
- [ ] 写 `test_config.py::test_provider_preferences_round_trip`：`save` → `get` 读回同一个 `tmp_path` 文件
- [ ] 写 `test_config.py::test_provider_preferences_never_erase_key`：payload 里 `deepseek_api_key` 为空白 → 磁盘上的旧值**保持不变**
- [ ] 写 `test_config.py::test_provider_preferences_fall_back_on_corrupt_file`：文件内容不是合法 JSON → 返回默认值，**不抛异常**
      （同一个测试里再覆盖**非 UTF-8 字节**的文件：读文件时的 `UnicodeDecodeError` 也必须被吞掉，同样返回默认值。
      「不抛异常」是契约，不是「不抛 JSONDecodeError」。）
- [ ] 写 `test_config.py::test_provider_preferences_missing_file_returns_defaults`：文件**根本不存在** → 返回默认值，**不抛异常**
- [ ] 写 `test_config.py::test_provider_preferences_file_is_written_with_restrictive_permissions`：断言落盘文件的
      `stat.S_IMODE(...) == 0o600`；**在 Windows 上跳过**（Windows 的 `os.chmod` 只切换只读属性，产生不了 POSIX 权限位）
- [ ] **测试隔离**：`provider_preferences_path` 必须指向 `tmp_path`，**绝不允许**写进仓库真实的 `.course-agent/`（用 `monkeypatch.setattr(Settings, "provider_preferences_path", ...)` 打桩）
- [ ] 再跑 → PASS
- [ ] 提交：`git commit -m "feat: 建立 Settings 配置系统"`

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_config.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_config.py -v
```

<details><summary>P0.2.1 · <code>Settings</code> 的 29 个字段（名称 · 类型 · 默认值）</summary>

```python
llm_provider: str = "codex_gateway"
llm_model: str = "llm-gateway--kimi-k3"
deepseek_api_key: str = ""
llm_base_url: str = ""
codex_gateway_config_path: str = "~/.codex/config.toml"
codex_gateway_reasoning_effort: str = "medium"
codex_gateway_service_tier: str = "standard"
llm_timeout_seconds: int = 90
llm_call_hard_timeout_seconds: int = 210
llm_long_content_hard_timeout_seconds: int = 600
llm_humanizer_hard_timeout_seconds: int = 720
llm_semantic_review_hard_timeout_seconds: int = 360
llm_continuity_hard_timeout_seconds: int = 180
llm_max_output_tokens: int = 32768
llm_chapter_max_output_tokens: int = 32768
llm_mission_max_output_tokens: int = 32768
llm_blueprint_max_output_tokens: int = 32768
llm_research_max_output_tokens: int = 32768
llm_workspace_audit_max_output_tokens: int = 32768
llm_presentation_max_output_tokens: int = 32768
llm_semantic_review_max_output_tokens: int = 32768
llm_continuity_max_output_tokens: int = 32768
llm_structured_output_retry_count: int = 2
chapter_quality_max_attempts: int = 2
quality_cycle_max_discovery_sweeps: int = 2
chapter_writer_max_attempts: int = 3
course_agent_max_concurrent_runs: int = 1
worker_poll_interval_seconds: float = 1.0
worker_lease_seconds: int = 45
```

> 为什么 Phase 0 就把 29 个字段全建好：Phase 0 的目标就是「让后面 8 个阶段只写业务代码」。
> P3.4 / P3.5 的测试直接引用了其中的旋钮（章节生成 `max_tokens == 32768`、
> `humanize` 用 `hard_timeout_seconds == 720`、规划类超时 600s），这些字段
> 不在 P0.2 定义，后面的计划就只能临时发明名字，代码会偏离目标版。

</details>

<details><summary>P0.2.2 · <code>get_provider_preferences()</code> / <code>save_provider_preferences()</code> 契约</summary>

两个函数都由 P7.5（`PUT /api/settings/provider`）消费，**不是**死代码。

```python
def get_provider_preferences(settings: Settings | None = None) -> dict[str, Any]:
    # defaults = {provider, model, deepseek_api_key, llm_base_url}，取值来自 Settings
    # path = settings.provider_preferences_path
    # 文件不存在 → 返回 defaults
    # 文件不是合法 JSON → 返回 defaults（**不抛异常**）
    # 文件内容不是 dict → 返回 defaults
    # 否则 {**defaults, **{k: v for k, v in stored.items() if v is not None}}

def save_provider_preferences(payload: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    # allowed = {"provider", "model", "deepseek_api_key", "llm_base_url"}；不在其中的 key 一律丢弃
    # deepseek_api_key 传空白字符串 → **不写入**（UI 里的空输入 = 保留旧密钥，不是擦除）
    # path.parent.mkdir(parents=True, exist_ok=True)
    # 先写 path.with_suffix(".tmp")，再 os.replace(temporary, path)（原子替换）
    # 写完临时文件后 os.chmod(temporary, 0o600)——这个文件里存着 DeepSeek 密钥
    # 写入内容用 json.dumps(merged, ensure_ascii=False, indent=2)
    # 返回合并后的完整 dict
```

- 落盘文件名固定为 **`provider-settings.json`**（连字符），路径
  `<repo_root>/.course-agent/provider-settings.json`。
- 存储的是**本地偏好**，永远不进课程产物、不进 Git。

</details>


#### P0.3 · 提供 `.env.example` 与 Provider 配置面

**产出**：一份 11 项环境变量模板，启动脚本据此校验凭据。

**文件**
- Create: `apps/api/.env.example`
- Modify: `apps/api/tests/test_config.py`（P0.2 建的那个文件，本任务往里加一条测试）

**接口**
- Consumes: P0.2 的 `Settings` 字段名
- Produces: `.env.example` 内容（见下方附录 P0.3.1）

**步骤**
- [ ] 先写 `test_config.py::test_env_example_covers_every_settings_field`：读 `.env.example`，断言**模板里的每个 key 都是一个 `Settings` 字段名**（`LLM_PROVIDER` → `llm_provider`）。
      模板路径用测试文件自身定位：`Path(__file__).resolve().parents[1] / ".env.example"`（`parents[1]` = `apps/api/`）。
      解析模板时跳过空行和以 `#` 开头的注释行，取每行 `=` 左边当 key。
- [ ] 跑测试 → **FAIL**（`.env.example` 还不存在）
- [ ] 按下方附录 P0.3.1 逐行写入 `apps/api/.env.example`（**逐字照抄，包括 2 行注释**）
- [ ] 再跑 → **PASS**
- [ ] 提交：`git commit -m "chore: 提供环境变量模板"`
      **提交时 `git add` 这两个路径**：`apps/api/.env.example` 和 `apps/api/tests/test_config.py`。
      不要用 `git add -A` / `git add .`。

> ⚠️ 断言方向是**单向**的（模板 ⊆ 字段），不是双向。P0.2 定义了 29 个字段，
> 而模板只有 9 个变量——剩下 20 个是内部旋钮（各类超时、max_output_tokens、
> 重试次数），有合理默认值，**刻意**不做成环境变量。反向断言（字段 ⊆ 模板）
> 连目标版自己都过不了。单向断言已经能抓住两类真实故障：模板里的 key 拼错、
> 以及 `Settings` 字段改名后模板没跟着改。

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_config.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_config.py -v
```

<details><summary>P0.3.1 · <code>.env.example</code> 精确内容</summary>

```bash
LLM_PROVIDER=codex_gateway
LLM_MODEL=llm-gateway--kimi-k3
# Reads base_url and token from ~/.codex/config.toml. Do not copy the token here.
CODEX_GATEWAY_CONFIG_PATH=~/.codex/config.toml
CODEX_GATEWAY_REASONING_EFFORT=medium
CODEX_GATEWAY_SERVICE_TIER=standard
# Optional fallback provider.
DEEPSEEK_API_KEY=
LLM_BASE_URL=
LLM_TIMEOUT_SECONDS=90
COURSE_AGENT_MAX_CONCURRENT_RUNS=1
```
</details>

#### P0.4 · 建立根 `package.json` 与契约测试骨架

**产出**：仓库根有了 npm 入口，`npm run test:contract` 从第一天起就是绿的。

**文件**
- Create: `package.json`（仓库根）
- Create: `tests/course-structure-contract.test.mjs`（占位版，1 条冒烟测试）

**接口**
- Consumes: 无
- Produces: 根脚本 `test:contract` = `node --test tests/course-structure-contract.test.mjs`；`check:source-size` = `node scripts/check-source-size.mjs`；唯一依赖 `mdast-util-from-markdown@2.0.3`（精确版本）

**步骤**
- [ ] 按下方附录 P0.4.1 写入 `package.json`（`private: true` · `type: "module"`）
- [ ] 写 `tests/course-structure-contract.test.mjs` 占位版：`import test from "node:test"` + `import assert from "node:assert/strict"`，1 条测试断言根 `package.json` 的 `scripts.test:contract` 存在
- [ ] 跑 `npm install` → 生成 `node_modules/`
- [ ] 跑 `npm run test:contract` → PASS
- [ ] 提交：`git commit -m "chore: 建立根级 npm 工具入口"`

**验收**
```bash
npm run test:contract
```

<details><summary>P0.4.1 · 根 <code>package.json</code> 精确内容</summary>

```json
{
  "name": "ai-course-studio-tools",
  "private": true,
  "type": "module",
  "scripts": {
    "test:contract": "node --test tests/course-structure-contract.test.mjs",
    "check:source-size": "node scripts/check-source-size.mjs"
  },
  "dependencies": {
    "mdast-util-from-markdown": "2.0.3"
  }
}
```

> 根目录**没有** `build` 脚本，也**没有** `test` 脚本——只有上面两个。
> 精确钉版本（不用 `^`），因为 `validate-course.mjs` 会跨目录 import `scripts/lib/`。
</details>

#### P0.5 · 建立 500 行规模门（脚本 + pytest 双入口）

**产出**：任何超过 500 行的生产源文件都会让 `pytest` 失败。

**文件**
- Create: `scripts/check-source-size.mjs`
- Create: `apps/api/tests/test_source_size.py`

**接口**
- Consumes: P0.4 的根 `package.json`
- Produces: `node scripts/check-source-size.mjs`（退出码 0 = 通过）；`pytest::test_production_source_size_gate_passes`

**步骤**
- [ ] 写 `test_source_size.py::test_production_source_size_gate_passes`：用 `subprocess.run(["node", "scripts/check-source-size.mjs"], cwd=repo_root, capture_output=True, text=True, check=False)` 跑，断言 `returncode == 0`。
      **`repo_root` 从测试文件自身定位**：`Path(__file__).resolve().parents[3]`（`parents[3]` = 仓库根，因为本文件在 `apps/api/tests/`）。
      **必须传 `cwd=repo_root`** —— 这样无论从哪个目录调用 pytest，测试都能过。
- [ ] 跑测试 → FAIL（脚本不存在）
- [ ] 实现 `scripts/check-source-size.mjs`（语义见下方附录 P0.5.1）
- [ ] 再跑 → PASS
- [ ] **手工验证门禁真的会拦**：临时在 `apps/api/app/` 造一个 501 行的 `.py`，跑测试 → 必须 FAIL；**删掉临时文件**
      （临时文件请写成**合法的 Python**（比如重复同一行注释），否则 `ruff check apps/api` 会因为它报错；
      或者在做 Ruff 检查之前就把它删掉。）
- [ ] **确认没有留下任何临时文件**：`git status --short` 必须是干净的（临时文件是未跟踪状态，留着就会混进提交）
- [ ] 提交：`git commit -m "chore: 建立生产源码行数门禁"`
      **提交时 `git add` 这两个路径**：`scripts/check-source-size.mjs` 和 `apps/api/tests/test_source_size.py`。
      不要用 `git add -A` / `git add .`。

**验收**
```bash
node scripts/check-source-size.mjs
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_source_size.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_source_size.py -v
```

<details><summary>P0.5.1 · <code>check-source-size.mjs</code> 精确语义</summary>

```js
const MAX_LINES = 500;
const sourceRoots = ["apps/api/app", "apps/web/src"];
const extensions = new Set([".py", ".ts", ".tsx", ".css"]);
```

- 行数 = `source.split("\n").length - (source.endsWith("\n") ? 1 : 0)`（结尾换行不计入）。
- **扫描范围精确为两个根目录**：`apps/api/app` 与 `apps/web/src`；
  **扩展名精确为四个**：`.py / .ts / .tsx / .css`。
  `.mjs / .js / .json / .md` **不检查**；`apps/web/tests/`、`apps/api/tests/`、`scripts/`、`tests/` **不检查**。
- **必须递归遍历子目录**：两个根下面都有子目录（`apps/api/app/api/course_routes.py`、
  `apps/web/src/components/layout.tsx`），只扫一层会漏掉它们。
  判断文件类型用 `entry.isDirectory()` 递归、`extensions.has(扩展名)` 过滤。
- **某个根目录不存在时跳过它**（当作 0 个文件），不要因为 `readdir` 抛 ENOENT 而崩溃。
  目标版在这里没有防护（它会直接抛异常），这是本仓库刻意做的一处加固：门禁脚本因为
  目录缺失而崩掉，输出的是一堆栈，不是"哪里超了 500 行"。
- **仓库根从脚本自身位置推导**，不要用 `process.cwd()`：
  `fileURLToPath(import.meta.url)` → `scripts/` 的上一级就是仓库根。
  然后 `sourceRoots` 按这个仓库根拼成绝对路径，输出路径用 `relative(repoRoot, file)`。
  这样从任何目录运行脚本都能扫到正确的目录、打印出的路径也始终是**相对仓库根**的
  （`npm run check:source-size` 会把 cwd 设成包根，所以常规用法下输出与用 `process.cwd()` 完全一样）。
- 违规时打印 `Production source files must not exceed 500 lines:`，
  随后按行数降序列出 `- <相对路径>: <行数>`，并 `process.exitCode = 1`。
- 通过时打印 `Source size check passed (N files, <= 500 lines each).`
</details>

#### P0.6 · 更新 `.gitignore` 与前端依赖

**产出**：敏感目录不进 Git；前端 9 个新依赖就位。

**文件**
- Modify: `.gitignore`（**预期无需改动** —— 见下方说明）
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`（`npm install` 会重写它，**必须一起提交**）

**接口**
- Consumes: P0.1
- Produces: 忽略项 `.course-agent/` · `.venv/` · `node_modules/` · `.pytest_cache/` · `apps/api/.env`；前端依赖 `@tanstack/react-query@5.101.2` · `@xyflow/react@^12.11.2` · `framer-motion@12.38.0` · `lucide-react@0.468.0` · `mermaid@^11.16.0` · `react-markdown@10.1.0` · `react-syntax-highlighter@^16.1.1` · `remark-gfm@4.0.1` · `@types/react-syntax-highlighter@^15.5.13`（**放 `devDependencies`**）

**步骤**
- [ ] 确认 `.gitignore` 含上面 5 类忽略项；**保留当前仓库额外的 `.docs/specs/`**（目标版把它删了）。**当前 `.gitignore` 已经全部覆盖这 5 类，预期 `.gitignore` 没有任何改动** —— 只需验证并在报告里写明「已覆盖，无须改动」，不要为了"有改动"而乱改它。
- [ ] 在 `apps/web/package.json` 的 `dependencies` 写入 8 个运行时依赖；在 `devDependencies` 写入 `@types/react-syntax-highlighter`
- [ ] 跑 `cd apps/web && npm install --offline` → 无冲突
  （**必须先 `cd` 进 `apps/web`**：`npm --prefix apps/web install` 会从当前目录向上找 `package.json`，在本仓库布局下会失败退出；`npm --prefix apps/web run typecheck` 这种 `run` 形式则是可以的。）
  （**用 `--offline`**：这 9 个包连同它们的全部传递依赖都已经在本机 npm 缓存里，
  `--offline` 强制 npm 只从缓存取、完全不联网、不碰任何远端包源。
  生成的 `package-lock.json` 与联网安装产生的是同一个文件 —— `resolved` / `integrity`
  都由缓存里那份 packument 决定，与是否联网无关。）
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error
- [ ] `git status --short` → 确认 `.venv/`、`node_modules/` 不出现
- [ ] 提交：`git commit -m "chore: 补齐前端依赖与忽略规则"`
  **提交时要 `git add` 这三个路径**：`apps/web/package.json`、`apps/web/package-lock.json`、以及（若有改动的）`.gitignore`。
  `apps/web/package-lock.json` 已经被上一轮提交纳入版本控制，`npm install` 一定会重写它 —— 不提交就会留下一个脏工作树，且锁文件和清单对不上。
  **不要用 `git add -A` / `git add .`**，只按路径显式 `git add`。

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
git status --short
```

---

### Phase 1 · 七步 Happy Path V0

**阶段目标**：第一次跑通完整的产品形状。哪怕它跑在内存里、只生成一章、没有质量闭环。
**进入条件**：Phase 0 全部计划通过。
**退出条件**：`POST /api/courses` 能建课；七阶段在前后端一致可见；Fake Provider 能驱动失败路径。

#### P1.1 · 定义七阶段契约常量

**产出**：七阶段 id 与说明成为代码里的单一事实源。

**文件**
- Create: `apps/api/app/workflow/definitions.py`
- Create: `apps/api/app/workflow/__init__.py`
- Create: `apps/api/tests/test_workflow_definitions.py`

**接口**
- Consumes: P0.2
- Produces: `WORKFLOW_STEPS`（`list[dict[str, str]]`，7 个 dict，字段 `id` / `title` / `description` / `user_input` / `model_output`）；`STEP_ORDER`（`list[str]`）；`REVIEW_WORKFLOW_STEPS`（`list[dict[str, str]]`）；`REVIEW_STEP_ORDER`（`list[str]`）

**步骤**
- [ ] 写测试断言 `STEP_ORDER == ["intake","mission","blueprint","batch_plan","generation","quality","release"]`
- [ ] 写测试断言 `WORKFLOW_STEPS` 每个元素的 5 个键齐全（**恰好**这 5 个，不得多出别的键），且 `id` 顺序与 `STEP_ORDER` 一致
- [ ] 写测试断言 `REVIEW_STEP_ORDER` 与 `STEP_ORDER` 同序同长；`REVIEW_WORKFLOW_STEPS` 里 `quality` 的 `title` 是「课程 Review」（不同于新建课程的「整课质量闭环」），其余 6 步与 `WORKFLOW_STEPS` 逐字段相同
- [ ] 跑测试 → FAIL
- [ ] 实现 `definitions.py`
- [ ] 再跑 → PASS
- [ ] 提交：`git commit -m "feat: 定义七阶段契约常量"`

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workflow_definitions.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_workflow_definitions.py -v
npm run check:source-size
```

<details><summary>P1.1.1 · <code>WORKFLOW_STEPS</code> 的七条内容（目标版实测，逐字照抄）</summary>

七阶段的 id、顺序和文案是**产品契约**，不是实现细节：前端直接渲染这些字段，
§4.2 第 1 条也把它们钉死。因此下面 7 条 dict 的**字段和值逐字照抄**，
不得改写、翻译、增删字段或调整顺序。

```python
{
    "id": "intake",
    "title": "课程需求",
    "description": "确认课程目标、受众、范围、来源与交付形式",
    "user_input": "课程名称、受众、学习目标、内容范围、来源政策",
    "model_output": "结构化任务输入与缺失项",
},
{
    "id": "mission",
    "title": "任务定义",
    "description": "把课程想法变成可验收的任务",
    "user_input": "补充或修改全局课程要求；内容会同步影响后续所有工作区产物",
    "model_output": "MISSION.md 与假设清单",
},
{
    "id": "blueprint",
    "title": "模块与课程蓝图",
    "description": "按知识依赖和叙事连续性规划模块与章节",
    "user_input": "调整全局技术路线、模块、章节顺序、数量与学习成果",
    "model_output": "Module Context、章节计划与衔接关系",
},
{
    "id": "batch_plan",
    "title": "生成批次",
    "description": "沿模块边界组织可恢复的生成单元",
    "user_input": "确认或修改全局课程约束、批次、并发、预算和停止条件",
    "model_output": "批次列表与每批 Context Pack 范围",
},
{
    "id": "generation",
    "title": "批次生产循环",
    "description": "每批依次完成章节生成、三阶段质量门、返工与人工确认",
    "user_input": "处理当前批次问题、批准进入下一批，或要求定向返工",
    "model_output": "章节、质量门结果、连续性账本与批次进度",
},
{
    "id": "quality",
    "title": "整课质量闭环",
    "description": "汇总所有批次的未达标项，并仅定向修复受影响章节",
    "user_input": "确认整课质量结果，或对未通过章节发起统一定向修复",
    "model_output": "全课程质量汇总、待修复章节队列与闭环结果",
},
{
    "id": "release",
    "title": "整课确认",
    "description": "整课回归后交由用户决定是否完成",
    "user_input": "最终审核与发布决定",
    "model_output": "Markdown、HTML、质量记录和交付状态",
},
```

`REVIEW_WORKFLOW_STEPS`（Review 既有课程）复用第 1–5 步与第 7 步，
**只把第 6 步换成**下面这一条：

```python
{
    "id": "quality",
    "title": "课程 Review",
    "description": "审阅或重生成既有课程内容",
    "user_input": "选择章节、补充审阅要求并确认处理结果",
    "model_output": "章节审校、质量报告与修改结果",
},
```

两条硬性实现要求：

1. `STEP_ORDER` 与 `REVIEW_STEP_ORDER` **必须从 `WORKFLOW_STEPS` / `REVIEW_WORKFLOW_STEPS`
   推导**（如 `[step["id"] for step in WORKFLOW_STEPS]`），不得再手写第二份 id 列表——
   否则"单一事实源"就变成了两份事实。
2. `REVIEW_WORKFLOW_STEPS` 复用前 5 步与最后 1 步时**复用同一批 dict 对象**
   （`WORKFLOW_STEPS[:-2]` 与 `WORKFLOW_STEPS[-1]`），不要复制一份再改写。

</details>

#### P1.2 · 定义 Agent Protocol

**产出**：Agent 的能力边界先以协议固定下来，实现可以后补。

**文件**
- Create: `apps/api/app/agents/__init__.py`
- Create: `apps/api/app/agents/protocols.py`
- Create: `apps/api/tests/test_agent_protocols.py`

**接口**
- Consumes: P1.1
- Produces: `class CourseAgent(Protocol)`，含 `name: str` 与 **10 个**方法签名（见下方附录 P1.2.1；附录列的 17 个方法中，其余 7 个在 **P3.8** 随对应 Schema 一起补齐）

**步骤**
- [ ] 写测试断言 `CourseAgent` 是 `Protocol`，且 `__protocol_attrs__` **恰好**等于 `{"name"}` ∪ 本计划写入的 10 个方法名（**11 个**；附录的 17 个方法里另有 7 个属于 P3.8，届时才是 18 个）
- [ ] 跑测试 → FAIL
- [ ] 实现 `protocols.py`，**只写签名与 `...`，不写实现**；模块顶部写 `from __future__ import annotations`，**不要 import 任何输出 Schema**（见附录说明）
- [ ] 再跑 → PASS
- [ ] 提交：`git commit -m "feat: 定义 Agent 协议"`

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_agent_protocols.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_agent_protocols.py -v
```

<details><summary>P1.2.1 · <code>CourseAgent</code> 的 17 个方法（目标版实测）</summary>

```python
class CourseAgent(Protocol):
    name: str
    def create_mission(self, request: dict) -> MissionOutput: ...
    def revise_workspace(self, mission: str, feedback: str) -> WorkspacePatch: ...
    def create_blueprint(self, request: dict, mission: str) -> BlueprintOutput: ...
    def plan_research(self, request: dict, mission: str) -> ResearchPlanOutput: ...
    def curate_research(self, policy: str, candidates: dict) -> ResearchCurationOutput: ...
    def audit_workspace_consistency(self, request: dict) -> dict: ...
    def generate_chapter(self, context: dict) -> str: ...
    def humanize(self, markdown: str) -> HumanizerOutput: ...
    def semantic_review(self, markdown: str, context: dict) -> SemanticReviewOutput: ...
    def extract_continuity(self, markdown: str, context: dict) -> ContinuityOutput: ...
    def revise_chapter(self, markdown: str, feedback: str) -> str: ...
    def enrich_chapter(self, markdown: str, feedback: str) -> str: ...
    def plan_repair(self, task: dict, markdown: str, context: dict) -> RepairCapabilityPlan: ...
    def apply_repair_patch(self, markdown: str, patch: WorkspacePatch) -> str: ...
    def classify_reference_section(self, markdown: str) -> str: ...
    def rewrite_section(self, markdown: str, instruction: str) -> str: ...
    def present_output(self, step: str, label: str, output: dict) -> OutputPresentation: ...
```

> **本计划（P1.2）只写这 10 个**：
> `create_mission` · `create_blueprint` · `plan_research` · `curate_research` ·
> `generate_chapter` · `humanize` · `semantic_review` · `extract_continuity` ·
> `plan_repair` · `present_output`
>
> 其余 7 个（`revise_workspace` · `audit_workspace_consistency` · `revise_chapter` ·
> `enrich_chapter` · `apply_repair_patch` · `classify_reference_section` ·
> `rewrite_section`）在 **P3.8** 随对应 Schema 一起补齐。
>
> **输出 Schema 在本计划尚不存在。** 上面 10 个签名里的 `MissionOutput` ·
> `BlueprintOutput` · `ResearchPlanOutput` · `ResearchCurationOutput` ·
> `HumanizerOutput` · `SemanticReviewOutput` · `ContinuityOutput` ·
> `RepairCapabilityPlan` · `OutputPresentation` 都是 **P3.8** 的产物，
> `apps/api/app/schemas.py` 也在那时才被创建。因此本计划**一律不 import 它们**：
> 写了 `from __future__ import annotations` 之后，注解在运行期不会被求值，
> 未定义的名字是安全的；P3.8 再把 import 补上。

</details>

#### P1.3 · 实现 FakeProvider

**产出**：一个不需要密钥、不联网、输出确定、且**能按需制造失败**的 Agent 实现；顺带落地第一批输出 Schema，让 `FakeProvider` 的返回值是**真类型**而不是裸 `dict`。

**文件**
- Create: `apps/api/app/schemas.py`
- Create: `apps/api/app/agents/fake_runtime.py`
- Create: `apps/api/app/agents/runtime.py`
- Modify: `apps/api/app/agents/protocols.py`（补 9 个类型 import、删 9 个 `# noqa: F821`、加 `@runtime_checkable`、订正模块 docstring）
- Create: `apps/api/tests/test_schemas.py`
- Create: `apps/api/tests/test_fake_runtime.py`

**接口**
- Consumes: P1.2
- Produces:
  - `app/schemas.py` 的 **13 个**模型（附录 P1.3.1）：`MissionOutput` · `ChapterPlan` · `ModulePlan` · `BlueprintOutput` · `ResearchPlanOutput` · `CuratedSource` · `ResearchCurationOutput` · `HumanizerOutput` · `RepairTaskVerification` · `SemanticReviewOutput` · `ContinuityOutput` · `RepairCapabilityPlan` · `OutputPresentation`
  - `class FakeProvider`：`name = "fake"`，实现 P1.2 的 **10 个**方法（其余 7 个方法在 P3.8 随 Schema 一起补齐）
  - `create_course_agent(provider_name: str | None = None, model_name: str | None = None) -> CourseAgent`

**步骤**
- [ ] 写测试 `test_schemas.py`：`HumanizerOutput(score=30)` 合法、`HumanizerOutput(score=51)` 抛 `ValidationError`；`SemanticReviewOutput(score=90, decision="ready")` 合法、`decision="maybe"` 抛 `ValidationError`；`BlueprintOutput` 缺 `course_title` 抛 `ValidationError`
- [ ] 写测试 `test_fake_runtime.py`：`humanize()` 返回 `score == 47`；`semantic_review()` 返回 `decision == "ready"` 且 `score == 90`；`create_blueprint()` 返回**最多 4 章**（`preferred_chapter_count=12` → 4 章；`preferred_chapter_count=2` → 2 章；不传 → 4 章）
- [ ] 写测试：**失败路径可控** —— `FakeProvider(fail_at="generation")` 时 `generate_chapter()` 抛 `RuntimeError`；`FakeProvider(fail_at="humanize")` 时 `humanize()` 返回 `score == 30`（**合法**输出，不是异常）
- [ ] 写测试：同一个 `FakeProvider` 连续两次调用 `create_blueprint()` 返回**完全相同**的内容
- [ ] 写测试：工厂 `create_course_agent("fake")` 返回 `FakeProvider` 且 `isinstance(agent, CourseAgent) is True`；`create_course_agent("FAKE")` 同样返回 `FakeProvider`；`create_course_agent("codex_gateway")` 与 `create_course_agent()` 抛 `NotImplementedError`
- [ ] 写测试：`FakeProvider(fail_at="nope")` 抛 `ValueError`
- [ ] 跑测试 → FAIL
- [ ] 实现 `app/schemas.py`：**只写**附录 P1.3.1 的 13 个模型，**不要**加 `CourseCreate`（P1.5 才加）或 P3.8 的其余 Schema
- [ ] 实现 `fake_runtime.py`：`FakeProvider` 写 P1.2 的 10 个方法，返回值全部是 `app.schemas` 里的模型
- [ ] 实现 `runtime.py`：只做工厂（契约见附录 P1.3.2）
- [ ] 改 `protocols.py`：按附录 P1.3.3 补 import、删 `# noqa: F821`、加 `@runtime_checkable`
- [ ] 再跑 → PASS
- [ ] 提交：`git commit -m "feat: 实现 FakeProvider"`

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_fake_runtime.py apps/api/tests/test_schemas.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_fake_runtime.py apps/api/tests/test_schemas.py -v
npm run check:source-size
```

<details><summary>P1.3.1 · <code>app/schemas.py</code> 的 13 个输出模型（字段级契约）</summary>

模块顶部写 `from __future__ import annotations`，只 `from typing import Literal`（**不要** import `Any`——
本阶段没有用到它的模型）。每个模型都是一个 `pydantic.BaseModel`，字段如下（逐字段照抄，**不要**增删）：

```python
class MissionOutput(BaseModel):
    mission_markdown: str
    assumptions: list[str] = Field(default_factory=list)


class ChapterPlan(BaseModel):
    number: int
    title: str
    learning_outcome: str
    prerequisites: list[str] = Field(default_factory=list)
    continuity_in: list[str] = Field(default_factory=list)
    continuity_out: list[str] = Field(default_factory=list)
    pedagogy_type: Literal[
        "opening_closing",
        "environment",
        "language",
        "framework",
        "mechanism",
        "integrated_practice",
    ] = "language"
    primary_teaching_task: str = "概念讲解"
    instructor_voice: str = "耐心教练型"
    learning_path: list[str] = Field(default_factory=list)
    template_modules: list[str] = Field(default_factory=list)


class ModulePlan(BaseModel):
    title: str
    goal: str
    narrative: str
    chapters: list[ChapterPlan]


class BlueprintOutput(BaseModel):
    course_title: str
    modules: list[ModulePlan]
    design_notes: list[str] = Field(default_factory=list)


class ResearchPlanOutput(BaseModel):
    queries: list[str] = Field(default_factory=list)
    search_rationale: str = ""


class CuratedSource(BaseModel):
    title: str
    url: str
    reason: str
    source_type: Literal["official", "standard", "paper", "community"] = "official"


class ResearchCurationOutput(BaseModel):
    sources: list[CuratedSource] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HumanizerOutput(BaseModel):
    revised_markdown: str
    score: int = Field(ge=0, le=50)
    issues: list[str] = Field(default_factory=list)


class RepairTaskVerification(BaseModel):
    task_id: str
    resolved: bool
    evidence_excerpt: str = Field(default="", max_length=1200)
    reason: str = Field(default="", max_length=800)


class SemanticReviewOutput(BaseModel):
    score: int = Field(ge=0, le=100)
    decision: Literal["ready", "manual_review", "reject"]
    issues: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    repair_verifications: list[RepairTaskVerification] = Field(default_factory=list)


class ContinuityOutput(BaseModel):
    summary: str
    established_terms: list[str] = Field(default_factory=list)
    established_facts: list[str] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    bridge_to_next: list[str] = Field(default_factory=list)


class RepairCapabilityPlan(BaseModel):
    task_id: str
    scope: Literal["paragraph", "section", "chapter"] = "section"
    selected_capabilities: list[
        Literal[
            "markdown_format",
            "link_reference",
            "code_structure",
            "teaching_scaffold",
            "source_contract",
            "content_enrichment",
            "humanizer",
            "section_rewrite",
            "chapter_rewrite",
        ]
    ] = Field(default_factory=list, max_length=4)
    target_anchors: list[str] = Field(default_factory=list, max_length=6)
    reasoning_summary: str = Field(min_length=1, max_length=800)
    verification_plan: list[str] = Field(default_factory=list, max_length=6)


class OutputPresentation(BaseModel):
    headline: str
    conclusion: str
    highlights: list[str] = Field(default_factory=list)
    metrics: dict[str, str | int | float | bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    next_action: str = ""
```

> `CourseCreate`（P1.5）、`WorkspacePatch` / `WorkspaceRevisionOutput` /
> `WorkspaceConsistencyOutput` / `HumanizerPatch` / `HumanizerPatchOutput` /
> `ReferenceSectionCandidate` / `ReferenceSectionDecision` / `RepairTextPatch` /
> `RepairPatchOutput` / `SectionRewriteOutput` / `EventPayload`（P3.8）**本阶段一律不写**。

</details>

<details><summary>P1.3.2 · <code>FakeProvider</code> 与工厂的行为契约</summary>

**输入契约**（缺键 → `KeyError`，不要用默认值兜底——fake 的输入面是刻意收紧的）：

| 方法 | 必需输入 | 可选输入 |
| --- | --- | --- |
| `create_mission(request)` | `request["title"]` · `request["audience"]` · `request["goals"]` · `request["scope"]` · `request["source_policy"]` | — |
| `create_blueprint(request, mission)` | `request["title"]` | `request["preferred_chapter_count"]`（默认 `4`） |
| `plan_research(request, mission)` | `request["title"]` | — |
| `curate_research(policy, candidates)` | — | `candidates["results"]`（缺 → 空列表） |
| `generate_chapter(context)` | `context["chapter"]["title"]` · `context["chapter"]["learning_outcome"]` | `context["chapter"]["continuity_in"]` / `["continuity_out"]` |
| `humanize(markdown)` | `markdown` | — |
| `semantic_review(markdown, context)` | — | — |
| `extract_continuity(markdown, context)` | — | `context["chapter"]`（缺 → 用兜底值） |
| `plan_repair(task, markdown, context)` | — | `task["id"]`（缺 → `"fake"`） |
| `present_output(step, label, output)` | `label` · `output` | `step`（本阶段**不**做特殊分支） |

**输出契约**：

- `create_mission()` → `mission_markdown` 以 `# {title}：课程任务定义` 开头，且含二级标题 `## 目标受众` ·
  `## 学习成果` · `## 内容范围` · `## 来源政策` · `## 交付与审核`；`assumptions == ["Fake Provider 演示输出"]`
- `create_blueprint()` → 章节数 `count = min(int(request.get("preferred_chapter_count", 4)), 4)`，
  **上限 4**；`course_title == request["title"]`；`modules` 恰好 1 个，`modules[0].title == "模块一：Fake Provider 演示模块"`；
  `design_notes == ["Fake Provider 仅用于本地演示，真实内容生成需要配置模型 Provider"]`
- `plan_research()` → `queries == [f"{request['title']} official documentation"]`；`search_rationale` 以 `Fake Provider` 开头
- `curate_research()` → `candidates` 无 `results` 时 `sources == []` 且 `notes == ["未获得可用网页候选。"]`；
  有 `results` 时 `sources` 恰好 1 条，取 `results[0]` 的 `title`（空则 `"检索结果"`）与 `url`，`source_type == "official"`
- `generate_chapter()` → 返回 markdown 以 `# {chapter['title']}` 开头，且含二级标题 `## 本章任务`
- `humanize()` → `HumanizerOutput(revised_markdown=markdown, score=47, issues=[])`
- `semantic_review()` → `score == 90`、`decision == "ready"`、`issues == []`、`strengths` 恰好 1 条
- `extract_continuity()` → `summary` 取 `chapter.get("learning_outcome", "Fake Provider 章节")`；
  `established_facts` 恰好 1 条；`bridge_to_next` 取 `chapter.get("continuity_out", [])`
- `plan_repair()` → `task_id == str(task.get("id", "fake"))`；`selected_capabilities == ["teaching_scaffold"]`；
  `target_anchors` 恰好 1 条；`verification_plan` 恰好 1 条；`reasoning_summary` 非空
- `present_output()` → `headline == f"{label}已完成"`；`highlights` 是 `output` 的**前 5 个**键（形如 `产出字段：{key}`）；
  `metrics == {"产出字段数": len(output)}`；`conclusion` 与 `next_action` 非空

**`fail_at` 失败注入**（`FakeProvider(fail_at=...)`，默认 `None` = 不注入失败）：

| `fail_at` | 触发的方法 | 行为 |
| --- | --- | --- |
| `"create_mission"` | `create_mission()` | 抛 `RuntimeError` |
| `"create_blueprint"` | `create_blueprint()` | 抛 `RuntimeError` |
| `"plan_research"` | `plan_research()` | 抛 `RuntimeError` |
| `"curate_research"` | `curate_research()` | 抛 `RuntimeError` |
| `"generation"`（别名）或 `"generate_chapter"` | `generate_chapter()` | 抛 `RuntimeError` |
| `"humanize"` | `humanize()` | **不抛异常**，返回 `HumanizerOutput(revised_markdown=markdown, score=30, issues` 恰好 1 条`)` |
| `"semantic_review"` | `semantic_review()` | 抛 `RuntimeError` |
| `"extract_continuity"` | `extract_continuity()` | 抛 `RuntimeError` |
| `"plan_repair"` | `plan_repair()` | 抛 `RuntimeError` |
| `"present_output"` | `present_output()` | 抛 `RuntimeError` |

- 抛 `RuntimeError` 时，消息固定为 `f"FakeProvider failed at {method_name}."`（`method_name` 是**方法名**，
  所以 `"generation"` 别名报的是 `FakeProvider failed at generate_chapter.`）
- `humanize` 是唯一**降级**而不是抛异常的一档：低分（30/50）是一个**合法但质量差**的输出，
  正好用来触发质量闭环，而不是把流程直接打断
- **其他任何 `fail_at` 值 → 构造时抛 `ValueError`**

**工厂 `create_course_agent(provider_name=None, model_name=None)`**：

- `provider_name` 为 `None` → 抛 `NotImplementedError`
- `provider_name.lower() == "fake"` → 返回 `FakeProvider()`
- 其他任何值 → 抛 `NotImplementedError`，消息固定为
  `f"Provider {provider_name!r} is not available in Phase 1; only 'fake' is implemented."`
- `model_name` 本阶段**保留但忽略**（fake 没有模型概念）

> **为什么默认也抛 `NotImplementedError`：** 本阶段**没有**真实 Provider——
> `AGENTS.md` 明确规定「未进入相应阶段前，不得提前加入 LLM Provider」。
> 参考实现会 fallback 到真实 Provider，但那条路在 Phase 1 还不存在，
> 照抄会让 `create_course_agent()` 变成一个永远走不通的假入口。

</details>

<details><summary>P1.3.3 · <code>app/agents/protocols.py</code> 的改动清单</summary>

P1.2 冻结协议时故意**没有** import 那些输出类型（它们当时还不存在），代价是 9 处
`# noqa: F821`。P1.3 建好 `app/schemas.py` 之后，这些标记必须收掉：

1. `from typing import Protocol` 改成 `from typing import Protocol, runtime_checkable`
2. 加上 `from app.schemas import (BlueprintOutput, ContinuityOutput, HumanizerOutput,
   MissionOutput, OutputPresentation, RepairCapabilityPlan, ResearchCurationOutput,
   ResearchPlanOutput, SemanticReviewOutput)`（9 个名字，一个不多一个不少）
3. **删掉 9 处 `# noqa: F821`**（`MissionOutput` · `BlueprintOutput` · `ResearchPlanOutput` ·
   `ResearchCurationOutput` · `HumanizerOutput` · `SemanticReviewOutput` ·
   `ContinuityOutput` · `RepairCapabilityPlan` · `OutputPresentation`）
4. `class CourseAgent(Protocol):` 改成 `@runtime_checkable` 装饰的
   `class CourseAgent(Protocol):`
5. 订正模块 docstring：把「这些类型是 P3.8 随 `app/schemas.py` 一起创建的」改成
   「这些类型由 P1.3 的 `app/schemas.py` 提供，P3.8 随其余 Schema 补齐剩余 7 个方法」；
   删掉「P3.8 replaces those markers with the real import」那句

> **`@runtime_checkable` 为什么现在加：** P1.3 第一次出现真实实现类，
> `isinstance(provider, CourseAgent)` 是「FakeProvider 实现了 CourseAgent」这条承诺
> 最直接的证据。注意它**只**支持 `isinstance`，**不支持** `issubclass`——
> `CourseAgent` 有 `name` 这个非方法成员，`issubclass(X, CourseAgent)` 会抛 `TypeError`。
> 测试里要用 `isinstance`，不要用 `issubclass`。

</details>

#### P1.4 · 建立路径护栏与原子写

**产出**：所有课程目录读写都有越界防护，JSON 写入是原子的。

**文件**
- Create: `apps/api/app/courses/__init__.py`（包标记，一行 docstring，同 `app/agents/__init__.py` 的写法）
- Create: `apps/api/app/courses/common.py`
- Create: `apps/api/tests/test_course_paths.py`

**接口**
- Consumes: P0.2
- Produces:
  - `SLUG_PATTERN: re.Pattern[str]` —— `re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")`
  - `_safe_course_root(slug: str, courses_root: Path) -> Path`
  - `_safe_child(root: Path, relative: str) -> Path`
  - `content_hash(text: str) -> str`（sha256 十六进制）
  - `_write_json_atomic(path: Path, payload: dict[str, Any]) -> None`

**写代码时的硬约定**
- `common.py` 顶部写 `from __future__ import annotations`，并且**必须** `from typing import Any`——
  `payload: dict[str, Any]` 用到了 `Any`。参考实现的 `courses/common.py` 漏了这个 import
  （因为注解是字符串所以没炸，但任何求值注解的工具都会 `NameError`），**这是已知缺陷，不要照抄**。
- `SLUG_PATTERN` 是 slug 校验的**唯一**正则来源。P1.5 的 `CourseCreate.slug` 必须用**同一个**模式串
  `^[a-z0-9]+(?:-[a-z0-9]+)*$`，P1.5 的测试要断言两者**逐字相同**——两边漂移就会出现
  「API 放行但护栏拒绝」或反过来的漏洞。
- 单行不超过 92 字符（中文按 2 个字符宽计算）；`ruff check` 必须干净。
- 新文件都要过 `npm run check:source-size`（单文件 500 行上限）。

**步骤**
- [ ] 写测试：`_safe_course_root("../etc", root)` → `ValueError("课程 slug 不合法")`；`"a/b"` · `"A"` · `"a_b"` · `""` · `"a b"` 同样被拒；`"python-101"` 通过并返回 `root / "python-101"`
- [ ] 写测试：`_safe_child(root, "../x")` → `ValueError("文件路径越界")`；`_safe_child(root, "a/../../b")` 同样被拒；`_safe_child(root, "..\\..\\b")`（Windows 反斜杠）同样被拒；`_safe_child(root, "/etc/passwd")`（绝对路径）同样被拒
- [ ] 写测试：`_write_json_atomic` 写完后文件是**完整**的 JSON，且 `ensure_ascii=False`（中文原样落盘，不转义成 `\uXXXX`）
- [ ] 写测试：`_write_json_atomic(path, payload)` 的中间文件叫 `path.with_suffix(path.suffix + ".tmp")`——`course.json` 对应 `course.json.tmp`（**不是** `course.tmp`）
- [ ] 写测试：用 `monkeypatch.setattr("app.courses.common.os.replace", ...)` 让替换步骤抛 `OSError`；断言①原文件内容**不变** ②目录里**不留下**任何 `.tmp` 残留
- [ ] 写测试：`content_hash("")` == `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；同文本同哈希，不同文本不同哈希
- [ ] 跑测试 → FAIL
- [ ] 实现 `common.py`
- [ ] 再跑 → PASS
- [ ] 写一份改动说明（改了哪些文件、跑了哪些命令、结果如何）；**不要** `git add` / `git commit` / `git push`——提交由开发者自己做

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_course_paths.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_course_paths.py -v
npm run check:source-size
```

<details><summary>P1.4.1 · 四条护栏的判定规则（实现照此写，不要自行发挥）</summary>

**`_safe_course_root(slug, courses_root)`**

1. `SLUG_PATTERN.fullmatch(slug)` 不匹配 → `ValueError("课程 slug 不合法")`
   （**必须用 `fullmatch` 不能用 `match`**：Python 的 `$` 也会匹配「末尾换行符之前」，
   `match` 会放行 `"python-101\n"`，而 P1.5 的 Pydantic `pattern` 走 Rust regex 更严格、
   会先拒掉——同一个模式串两边口径必须一致，`SLUG_PATTERN` 才算数「唯一来源」）
2. 匹配则返回 `courses_root / slug`；返回前再用「结果仍在 `courses_root` 之内」复核一次，
   不通过也抛 `ValueError("课程 slug 不合法")`（双保险，slug 以后若被放宽也不会漏出目录）
3. `courses_root` 由调用方**显式传入**，不读 `Settings` 单例——这样护栏不用 monkeypatch 就能测

**`_safe_child(root, relative)`**

1. 先把 `relative` 里的 `\` 统一换成 `/`（Windows 上 `..\..\b` 同样是越界）
2. `relative` 是绝对路径（含 `C:\...`、`\\server\share`）→ `ValueError("文件路径越界")`
3. 拼出 `candidate = root / relative` 并 `resolve()`；若 `candidate` 不在 `root.resolve()` 之内
   → `ValueError("文件路径越界")`
4. 通过则返回 `candidate`

**`_write_json_atomic(path, payload)`**

1. **不**创建父目录——父目录必须已经存在，缺失时抛 `FileNotFoundError`（路径写错要立刻暴露，
   不能被悄悄 `mkdir` 掩盖）
2. 序列化用 `json.dumps(payload, ensure_ascii=False, indent=2)`，末尾补一个换行
3. 先写 `tmp = path.with_suffix(path.suffix + ".tmp")`（`course.json` → `course.json.tmp`），
   编码 `utf-8`
4. 再用 `os.replace(tmp, path)` 原子替换——**必须**用模块级的 `import os` 写 `os.replace`，
   测试要靠 `monkeypatch.setattr("app.courses.common.os.replace", ...)` 才能注入失败
5. 任何异常都要在抛出前删掉 `tmp`（`tmp.unlink(missing_ok=True)`），保证目录里不留 `.tmp`；
   原文件因为还没被替换而**保持原样**

**`content_hash(text)`**

- `hashlib.sha256(text.encode("utf-8")).hexdigest()`，返回 64 位小写十六进制

</details>

#### P1.5 · 实现课程脚手架创建

**产出**：建课时一次性铺好目录骨架与 `course.json`。

**文件**
- Modify: `apps/api/app/schemas.py`（加 `CourseCreate`——P1.3 的模块 docstring 已经写明「`CourseCreate` arrives with P1.5」；顺手把那句改掉）
- Create: `apps/api/app/courses/scaffold.py`
- Create: `apps/api/tests/test_course_scaffold.py`

**接口**
- Consumes: P1.4 的 `_safe_course_root` / `_write_json_atomic`
- Produces:
  - `app.schemas.CourseCreate`（P1.7 的 `POST /api/courses` 直接拿它当请求体）
  - `app.courses.scaffold.create_course_scaffold(request: CourseCreate, courses_root: Path) -> dict[str, Any]`
    （返回**刚落盘的**课程元数据字典 = `course.json` 的内容；
    `courses_root` 显式传入，不读 `Settings` 单例——理由同 P1.4 的 `_safe_course_root`）

**写代码时的硬约定**
- `CourseCreate` 的字段、默认值、取值范围**逐字照抄** P1.7「接口」段的那一串：
  `title` 2–120 · `slug` 正则 `^[a-z0-9]+(?:-[a-z0-9]+)*$` · `audience` 2–500 ·
  `goals` 5–3000 · `scope` 2–3000 ·
  `source_policy` 默认「允许使用用户资料与公开官方资料」· `delivery` 默认「Markdown + HTML」 ·
  `preferred_chapter_count` 默认 12（1–60）· `effective_char_min` 默认 12000（1000–50000）·
  `token_budget_mtokens` 可选（0.01–10000）· `provider` 默认 `codex_gateway` ·
  `model` 默认 `llm-gateway--kimi-k3`
- **`CourseCreate.slug` 的 `pattern` 必须与 `SLUG_PATTERN.pattern` 逐字相同**——P1.4 已经把
  `SLUG_PATTERN` 定成 slug 校验的唯一来源。写成两处字面量可以，但 P1.5 的测试**必须锁住**
  它们相等，否则 P1.7 的 API 放行、护栏拒绝。
- `course.json` 的键**固定为这 11 个**（多一个少一个都算错）：

  | 键 | 值 | 谁要读 |
  |---|---|---|
  | `schemaVersion` | `1` | 目标版 `course.json` 的既有字段 |
  | `slug` | `request.slug` | P1.6 目录扫描 · P1.7 |
  | `title` | `request.title` | P1.6 · P1.7 |
  | `description` | `request.goals` | P1.6 的目录项要 `description` |
  | `audience` | `request.audience` | 本计划 · P8.4 |
  | `goals` | `request.goals` | 本计划 · P8.4 |
  | `scope` | `request.scope` | 本计划 · P8.4 |
  | `duration` | `"待蓝图确认"` | 目录项也有 `duration` |
  | `status` | `"preparing"` | 目录项的 `status` |
  | `preferred_chapter_count` | `request.preferred_chapter_count` | P4.4 要把章节数同步进 `course.json` |
  | `lessons` | `[]` | P1.6 用 `len(lessons)` 算 `chapters` · P4.4 · P8.4 |

  目标版的 `course.json` 是 `slug`/`title`/`description`/`duration`/`status`/`audience`/`lessons`，
  **额外**带 `goals`/`scope`——P8.4 明确说「Consumes: P1.5 的 `course.json` 结构」，
  而 P8.4 产出的键里有 `goals`/`scope`，所以 P1.5 就得先写进去，不能等 P8.4 补。
- `course.json` **必须**用 P1.4 的 `_write_json_atomic` 写，**不要**用 `write_text` + `json.dumps`。
  参考实现用的是 `write_text`——写一半被读到就会拿到半截 JSON，**这是已知缺陷，不要照抄**。
- 目录骨架 = 6 个顶层目录 + 1 个子目录：
  `lessons/` · `reference/` · `markdown/` · `assets/` · `quality/` · `workspace/`
  ＋ `workspace/learning-records/`。
  `workspace/` 下 3 个文件：`NOTES.md` · `RESOURCES.md` · `COURSE-GENERATION-SPEC.md`；
  `reference/` 下 1 个文件：`glossary.md`。4 个文件的内容照 P1.5.1 附录抄。
- **P1.5 不许 import `app.courses.catalog`（P1.6 才建）也不许 import `app.courses.workspace`（P2.x 才建）。**
  参考实现的 `scaffold.py` 两个都 import 了，**这是已知缺陷，不要照抄**。
  `RESOURCES.md` 的正文在本文件里自己写死（见 P1.5.1），只有「来源政策」那一段用
  `request.source_policy` 填。
- slug 重复 → 抛 `FileExistsError`（**目录已存在就抛，不许覆盖已有课程**）。
- `scaffold.py` 里**每个函数**都要写文档注释（docstring：说明 / 参数 / 返回），
  格式照 P1.4 `common.py` 的四个函数。
- `from typing import Any` 必须 import（返回类型是 `dict[str, Any]`）。参考实现漏了，**不要照抄**。
- 单行不超过 92 字符（中文按 2 个字符宽计算）；`ruff check` 必须干净。
- 新文件都要过 `npm run check:source-size`（单文件 500 行上限）。
- **不要** `git add` / `git commit` / `git push`——提交由开发者自己做。

**步骤**
- [ ] 写测试：创建后 `courses/<slug>/` 下存在 `lessons/` · `reference/` · `markdown/` · `assets/` · `quality/` · `workspace/`，且 `workspace/learning-records/` 也在
- [ ] 写测试：`workspace/` 下存在 `NOTES.md` · `RESOURCES.md` · `COURSE-GENERATION-SPEC.md`；`reference/` 下存在 `glossary.md`
- [ ] 写测试：`course.json` 含 `slug` / `title` / `audience` / `goals` / `scope` / `status` / `lessons: []`，且 `status == "preparing"` · `description == goals` · `lessons == []`
- [ ] 写测试：`course.json` 的键**恰好**是「硬约定」表里那 11 个（多一个少一个都算失败）
- [ ] 写测试：`RESOURCES.md` 里有 `request.source_policy`；`COURSE-GENERATION-SPEC.md` 里有 `delivery` / `preferred_chapter_count` / `effective_char_min` 三个值
- [ ] 写测试：**slug 重复时抛 `FileExistsError`**，且**原目录里的文件一个都不许被改写**
- [ ] 写测试：`CourseCreate` 的 slug `pattern` 与 `SLUG_PATTERN.pattern` **逐字相同**
- [ ] 写测试：`CourseCreate` 拒绝非法输入（`title` 1 个字 / `audience` 1 个字 / `goals` 4 个字 / `scope` 1 个字 / `preferred_chapter_count=0` / `preferred_chapter_count=61` / `effective_char_min=999` / `effective_char_min=50001` / `slug` 含大写 / `slug` 含下划线）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 改 `app/schemas.py` 的模块 docstring：现在住着 14 个模型，把「`CourseCreate` arrives with P1.5」那句换成「P1.5 加进来的 `CourseCreate`」
- [ ] 写一份改动说明（改了哪些文件、跑了哪些命令、结果如何）；**不要** `git add` / `git commit` / `git push`——提交由开发者自己做

**验收**
```bash
# Linux / macOS
apps/api/.venv/bin/python -m pytest apps/api/tests/test_course_scaffold.py -v
# Windows
apps\api\.venv\Scripts\python.exe -m pytest apps/api/tests/test_course_scaffold.py -v
npm run check:source-size
```

<details><summary>P1.5.1 · 脚手架写出的 4 个文件（内容照抄，别自己发挥）</summary>

**`workspace/NOTES.md`**

```markdown
# 课程迭代笔记

本课程由课程生成 Agent 创建，当前处于引导模式。
```

**`workspace/RESOURCES.md`**（`{source_policy}` 换成 `request.source_policy`）

```markdown
# 课程资源

## 来源政策

{source_policy}

## 检索范围与使用边界

- Agent 会围绕课程核心概念、所用框架或工具的当前 API、相关标准或论文、项目实践与部署/安全边界检索资料。
- 每一条资料都必须说明其支撑的教学内容；关键事实、API 用法和规范不得只依赖未核验的社区文章。
- 资料是否可用以来源政策为准：只有政策允许时，才将社区教程作为补充阅读。

## Agent 检索与核验

任务定义确认后，Agent 会在这里写入检索计划、经筛选的资料和仍需人工补充的缺口。

## 用户补充资源

可在此登记链接、课程资料说明或上传附件的使用目的。
```

**`workspace/COURSE-GENERATION-SPEC.md`**

```markdown
# 课程生成规格

- 交付格式：{delivery}
- 期望章节数：{preferred_chapter_count}（供蓝图规划参考）
- 单章有效字符数下限：{effective_char_min}
- 运行模式：本地单用户、引导模式
- 质量门：逐章 Humanizer、构建、确定性检查、语义审校、人工确认
- 自动返工上限：同类问题连续三轮后转人工
```

**`reference/glossary.md`**

```markdown
# 术语表

| 术语 | 定义 |
| --- | --- |
```

</details>

#### P1.6 · 实现课程目录扫描与课程门面

**产出**：课程列表从文件系统扫描出来，不再依赖手写 `catalog.json`。

**文件**
- Create: `apps/api/app/courses/catalog.py`
- Create: `apps/api/app/course_service.py`
- Delete: `apps/api/app/catalog.py`
- Modify: `apps/api/app/api/course_routes.py`
- Modify: `apps/api/app/main.py`（`app/catalog.py` 删掉之后 `EXAMPLE_COURSE_ROOT` 没有出处了）
- Modify: `apps/api/app/schemas.py`（加 `CourseSummary` / `CourseList` 两个响应模型）
- Modify: `apps/api/tests/test_schemas.py`（模型清单加这两个）
- Create: `apps/api/tests/test_course_catalog.py`
- Create: `apps/api/tests/test_course_service.py`
- Modify: `apps/api/tests/test_scaffold_api.py`（旧的 `catalog.json` 断言要同步）
- Modify: `apps/web/src/api.ts`（`Course` 类型去掉 `href`）
- Modify: `apps/web/src/pages.tsx`（去掉指向 `course.href` 的那条死链）

**接口**
- Consumes: P1.5 落盘的 `course.json`（11 个键）
- Produces:
  - `app/courses/catalog.py::list_courses(courses_root: Path) -> list[dict[str, Any]]`
  - `app/courses/catalog.py::get_course(slug: str, courses_root: Path) -> dict[str, Any] | None`
  - `app/course_service.py::list_courses() -> list[dict[str, Any]]`（门面，root 来自 `Settings`）
  - `app/course_service.py::get_course(slug: str) -> dict[str, Any] | None`（门面）
  - `app/schemas.py::CourseSummary` / `app/schemas.py::CourseList`
  - `GET /api/courses` → `{"items": [...]}`；`GET /api/courses/{slug}` → 一项 / 404 / 400

**写代码时的硬约定**

**目录项的形状——恰好 6 个键，一个不多一个不少：**

| 键 | 从哪儿来 | 说明 |
| --- | --- | --- |
| `slug` | 课程文件夹名 | 文件夹名就是课程的地址；`course.json` 里的 `slug` 与它同值（P1.5 两处都写 `request.slug`） |
| `title` | `course.json` 的 `title` | 缺失时退回文件夹名 |
| `description` | `course.json` 的 `description` | P1.5 写进去的是 `request.goals`；缺失时是空串 |
| `chapters` | `len(course.json` 的 `lessons`)` | `lessons` 不是列表时算 0 |
| `status` | `course.json` 的 `status` | 缺失时是 `"preparing"` |
| `duration` | `course.json` 的 `duration` | 缺失时是空串 |

**目录项里没有的东西（别加）：** `href` · `audience` · `goals` · `scope` ·
`preferred_chapter_count` · `lessons` 本身。

- **`href` 为什么消失**：老 `catalog.json` 里的 `href` 是手写的 `/course-example/`，
  指向**唯一那一个**手挂的静态示例。改成扫描之后，每门课都可能有 `index.html`，
  但 API 现在**没有**按课程提供静态页的路由（P8.1 的构建 + 按课程发布才会给），
  硬造一个 `href` 就是造一个 404 的地址。前端卡片那条链因此先拿掉，
  P1.8 会用真正的 `/courses/:slug` 路由把它加回来。
- **`courses/catalog.json` 这个文件留着**，只是 API 不再读它了——
  它以后只当**发布索引**（P8.x 的 `publish_course` 往里写）。
  这条同时解掉「目标版已知缺陷 #9：catalog.json 与 API 课程列表是两个独立来源」。

**扫描时跳过什么（跳过 ≠ 报错）：**

1. 没有 `course.json` 的子目录 → 跳过（课程还在建，没到落盘那一步）。
2. `course.json` 读不出来 / 不是合法 JSON / 不是一个对象 → 跳过。
   **一个坏掉的课程不能拖垮整个列表**——列表接口是给人看的，不是给错误页看的。
3. 以 `.` 开头的文件夹 → 跳过（隐藏目录）。
4. 文件夹名不匹配 `SLUG_PATTERN` 的目录 → 跳过。
   这种目录没法用地址访问（`get_course` 会抛 `ValueError`），
   留在列表里就是一门「点不开的课程」。

**两种「找不到」要分清：**

| 情况 | `catalog.get_course` | 路由层 |
| --- | --- | --- |
| slug **合法**但没有这门课 | 返回 `None`，**不抛异常** | 404 |
| slug **不合法**（`../etc`、`Python-101`） | 抛 `ValueError("课程 slug 不合法")` | 400 |

P1.4 的路径护栏不能被绕过：`get_course` 内部**必须**走
`app.courses.common._safe_course_root(slug, courses_root)`，
不要自己拼路径。

**分层职责：**
- `app/courses/catalog.py`：**唯一**读 `course.json` 的地方。`courses_root` **显式传参**，
  不读 `Settings`（跟 P1.4 / P1.5 同一个规矩）。
- `app/course_service.py`：门面。`list_courses()` / `get_course(slug)` 从
  `get_settings().courses_root` 拿到 root 再转手给 `catalog`。
  路由只认门面，不直接 import `catalog`。
- `app/api/course_routes.py`：只做「调门面 → 变成 HTTP 响应」。

**不许 import 的东西（还没到那个阶段）：**
`app.courses.quality`（P5.x）· `app.courses.workspace`（P2.x）· `app.courses.chapters`（P3.x）·
`app.courses.tools`（P4.x）· `app.db`（P2.1）· `app.workflow.*`（P2.x 起）·
`app.agents.*` 之外的任何 LLM Provider 入口。

**参考实现不要照抄的四处：**
1. 参考的 `list_courses()` 读 `Settings` 单例、还 import 了 `app.courses.quality` 和 `app.db`——
   那是 P5.x / P2.1 的东西，本阶段拿不到。
2. 参考的目录项叫 `chapter_count`、还带一堆 `quality_report_count` / `has_workspace` /
   `has_course_json` / `lessons`——本阶段的目录项就是上面那张 6 键表。
3. 参考的 `get_course()` 找不到就抛 `FileNotFoundError`；本阶段是**返回 `None`**。
4. 参考的 `list_courses()` 把**没有 `course.json` 的目录也列出来**（靠 `has_course_json` 标记）——
   本阶段是**直接跳过**。

**其它约定：**
- 每个函数都要写完整文档注释（说明 + `Args` + `Returns`），中文说明、英文标识符。
- `from typing import Any` 别漏（返回类型是 `dict[str, Any]`）。
- 单行不超过 **92** 字符（中文按 2 列算）。
- `npm run check:source-size` 过了（新文件都远低于 500 行）。
- **不要** `git add` / `git commit` / `git push`——提交由开发者自己做。

**步骤**
- [ ] 写 `test_course_catalog.py`：扫描 `courses/*/course.json`，每项含 `slug` / `title` /
      `description` / `chapters` / `status` / `duration`，**恰好这 6 个键**
- [ ] 写 `test_course_catalog.py`：`get_course("不存在的 slug")` → `None`，**不抛异常**
- [ ] 写 `test_course_catalog.py`：目录里没有 `course.json` 的子目录被**跳过**，不报错
- [ ] 写 `test_course_catalog.py`：`course.json` 坏掉的课程被跳过，其它课程照常列出
- [ ] 写 `test_course_catalog.py`：隐藏目录、非法文件夹名被跳过；root 不存在时返回空列表
- [ ] 写 `test_course_catalog.py`：`get_course` 传非法 slug → `ValueError`（路径护栏没被绕过）
- [ ] 写 `test_course_service.py`：门面从 `Settings.courses_root` 拿 root（用 `monkeypatch`
      换掉 `app.course_service.get_settings`，指向 `tmp_path`）
- [ ] 跑测试 → FAIL → 实现 `catalog.py` + `course_service.py` → PASS
- [ ] 加 `CourseSummary` / `CourseList` 到 `app/schemas.py`，同步 `test_schemas.py` 的模型清单
- [ ] 改 `course_routes.py` 走门面：列表 + `GET /api/courses/{slug}`（404 / 400）
- [ ] 删掉 `app/catalog.py`，改 `app/main.py` 的 `EXAMPLE_COURSE_ROOT` 出处
      （用 `get_settings().courses_root / "advanced-learning-of-obsidian"`）
- [ ] 同步 `test_scaffold_api.py`：旧的 `catalog.json` 断言改成扫描后的形状
- [ ] 改前端：`api.ts` 的 `Course` 去掉 `href`，`pages.tsx` 去掉那条死链
- [ ] 跑 `pytest apps/api/tests` → 全绿
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error；`run build` → 成功
- [ ] 写一份改动说明到 `docs/changes/2026-10-27/`（格式照 `.claude/skills/code-change-report/SKILL.md`，
      报告里出现的函数都要带文档注释）
- [ ] **不要** `git add` / `git commit` / `git push`——提交由开发者自己做

**验收**
```bash
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -v
apps/api/.venv/bin/python -m pytest apps/api/tests -v
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm run check:source-size
curl http://127.0.0.1:8000/api/courses
```

#### P1.7 · 暴露 `POST /api/courses`

**产出**：建课有 API 入口，三种失败各有明确状态码。

**文件**
- Modify: `apps/api/app/api/course_routes.py`（加 `POST /api/courses`）
- Modify: `apps/api/app/course_service.py`（**计划外**：门面加 `create_course(request)`——
      P1.6 的分层规则要求路由只跟门面说话，路由不能自己拿 `courses_root`）
- Modify: `apps/api/app/schemas.py`（加 `CourseCreated` 响应模型）
- Modify: `apps/api/tests/test_schemas.py`（模型清单加 `CourseCreated`）
- Create: `apps/api/tests/test_course_create_api.py`

**接口**
- Consumes: P1.6 的 `course_service` 门面；P1.5 的 `create_course_scaffold(request, courses_root)`
  与 `CourseCreate`
- Produces:
  - `app/course_service.py::create_course(request: CourseCreate) -> dict[str, Any]`（门面）
  - `app/schemas.py::CourseCreated`（`course` / `run_id` / `status` 三个键）
  - `POST /api/courses` → 201 `{"course": {…6 键…}, "run_id": "<uuid4>", "status": "preparing"}`；
    409 / 422 / 400
- `CourseCreate` 本步**不改**：字段约束 P1.5 已经逐字实现
  （`title` 2–120 · `slug` 正则 `^[a-z0-9]+(?:-[a-z0-9]+)*$` · `audience` 2–500 ·
  `goals` 5–3000 · `scope` 2–3000 · `source_policy` 默认「允许使用用户资料与公开官方资料」·
  `delivery` 默认「Markdown + HTML」· `preferred_chapter_count` 默认 12（1–60）·
  `effective_char_min` 默认 12000（1000–50000）· `token_budget_mtokens` 可选（0.01–10000）·
  `provider` 默认 `codex_gateway` · `model` 默认 `llm-gateway--kimi-k3`）。

**写代码时的硬约定**

**响应的三个键：**

| 键 | 值 | 说明 |
| --- | --- | --- |
| `course` | P1.6 那 6 个键（`slug` / `title` / `description` / `chapters` / `status` / `duration`） | 落盘之后**从磁盘读回来**，所以跟 `GET /api/courses` 里那门课**一模一样**；不手拼、不镜像 `course.json` 的 11 个键 |
| `run_id` | `str(uuid.uuid4())` | 本步只发一个 id，**不落库**——Run 表是 P2.1 的事 |
| `status` | `"preparing"` | 这门课的**状态**，跟 `course.status` 同一个值：建好了，但还没有章节 |

- `course` 用 `CourseSummary` 那 6 个键，**不是** `course.json` 的 11 个键。
  11 个键的契约已经被 P1.5 的测试锁住，再在 `schemas.py` 里抄一份就是第二个事实源。
  前端也只有一个 `Course` 类型（P1.8 要用），建课响应和列表响应用同一个形状才对得上。
- `run_id` 现在是**占位**：本阶段没有 Run 表、没有事件、没有队列，这个 id 落不了地、查不到东西。
  P2.1 建了 `runs` 表之后由它接管。**不要在报告里把它说成「已经有一次运行」。**

**三种失败，各有各的状态码：**

| 情况 | 谁拦的 | 状态码 |
| --- | --- | --- |
| slug **已被占用** | `create_course_scaffold` 抛 `FileExistsError` | **409** |
| slug **不合法**（大写 / 含空格 / 含下划线） | Pydantic 校验 `CourseCreate.slug` | **422** |
| 其它字段越界（`title` 只有 1 个字…） | Pydantic 校验 | **422** |
| 路径护栏拒绝（安全网，正常到不了） | `_safe_course_root` 抛 `ValueError` | **400** |

- **409 必须按异常类型判断**（`except FileExistsError`），**不许拿异常文案去比对**——
  文案会被人改，按类型判断才不会。
- 422 是 Pydantic 自己的校验错误（`RequestValidationError`），不用自己写。
- 400 是安全网：slug 已经被 Pydantic 拦成 422 了，走到这里说明有别的路径漏进来了。

**分层职责（跟 P1.6 同一套）：**
- `app/course_service.py`：门面。`create_course(request)` 从 `get_settings().courses_root`
  拿到 root，转手给 `scaffold.create_course_scaffold(request, root)`，落盘后**再从磁盘读回来**
  那 6 个键。
- `app/api/course_routes.py`：只做「调门面 → 变成 HTTP 响应」。路由**不 import**
  `app.courses.scaffold`，**不 import** `app.courses.catalog`，也**不自己**拿 `courses_root`。

**参考实现不要照抄的四处：**
1. 参考的 POST 路由同时做：建 run record（`create_run_record`）、写 artifact
   （`record_run_artifact`）、入队命令（`enqueue_command`）——那是 P2.1 / P2.2 / P6.x 的东西，
   本阶段拿不到。**不许提前 import。**
2. 参考的响应是 `{course, run_id, command_id, duplicate}`；本阶段的契约是
   `{course, run_id, status}`。`command_id` / `duplicate` 是命令队列的字段。
3. 参考的 `create_course_scaffold(payload)` 读 `Settings` 单例；本阶段是
   `create_course_scaffold(request, courses_root)`，root 由门面显式传进去。
4. 参考的 run 状态词汇是 `QUEUED`；本阶段**没有队列**，所以 `status` 是**课程**的状态
   `preparing`，不假装有排队这件事。

**测试约定：**
- 必须用 `monkeypatch.setattr("app.course_service.get_settings", ...)` 把 root 指向
  `tmp_path`——**不能在仓库真实的 `courses/` 里建课**，也不能污染示例课程。
- 走真实 `TestClient`（跟 `test_scaffold_api.py` 一样），测的是 HTTP 状态码，不是函数返回值。

**其它约定：**
- 每个函数都要写完整文档注释（说明 + `Args` + `Returns`），中文说明、英文标识符。
- `from typing import Any` 别漏（返回类型是 `dict[str, Any]`）。
- 单行不超过 **92** 字符（中文按 2 列算）。
- `npm run check:source-size` 过了（新文件都远低于 500 行）。
- **不要** `git add` / `git commit` / `git push`——提交由开发者自己做。

**步骤**
- [ ] 写 `test_course_create_api.py`：合法请求 → **201**；`course.slug` 对、
      `run_id` 非空、`status == "preparing"`；盘上落出了 `course.json` 和 6 个顶层目录
- [ ] 写测试：同一个 slug 建两次 → 第二次 **409**，而且原来那份 `course.json` **没被改**
- [ ] 写测试：slug 非法（大写 / 含空格 / 含下划线）→ **422**，而且**磁盘上什么都没留下**
- [ ] 写测试：`title` 只有 1 个字符 → **422**；其它字段越界（`audience` / `goals` / `scope` /
      `preferred_chapter_count` / `effective_char_min` / `token_budget_mtokens`）→ **422**
- [ ] 写测试：两个不同的合法请求 → 两个**不同**的 `run_id`
- [ ] 写测试：201 响应里的 `course` 跟 `GET /api/courses` 里那门课**完全一样**
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 门面加 `create_course(request)`：落盘后从磁盘读回那 6 个键
- [ ] `schemas.py` 加 `CourseCreated`，同步 `test_schemas.py` 的模型清单
- [ ] 路由加 `POST ""`（201）；409 按 `FileExistsError` 判、400 按 `ValueError` 判
- [ ] 跑 `pytest apps/api/tests` → 全绿
- [ ] 跑 `npm run check:source-size` → 过
- [ ] 写一份改动说明到 `docs/changes/2026-10-27/`（格式照 `.claude/skills/code-change-report/SKILL.md`，
      报告里出现的函数都要带文档注释）
- [ ] **不要** `git add` / `git commit` / `git push`——提交由开发者自己做

**验收**
```bash
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -v
apps/api/.venv/bin/python -m pytest apps/api/tests -v
npm run check:source-size
curl -X POST http://127.0.0.1:8000/api/courses -H 'Content-Type: application/json' \
  -d '{"title":"测试课程","slug":"test-course","audience":"有 Python 基础的学习者",
       "goals":"学会构建一个可恢复的 Agent","scope":"从零到发布","preferred_chapter_count":2}'
```

#### P1.8 · 前端：创建向导 + 课程详情路由

**产出**：用户能在浏览器里建课并跳到详情页。

**文件**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/pages.tsx` → 新建 `apps/web/src/pages/course-pages.tsx`
- Modify: `apps/web/src/styles.css`

**接口**
- Consumes: P1.7 的 `POST /api/courses`
- Produces: `api.createCourse(input: CourseCreate): Promise<{course, run_id, status}>`；路由 `/courses/:slug`

**步骤**
- [ ] 写 `api.ts` 的 `request<T>(path, init)` 包装器（支持 `init.body`），加 `CourseCreate` 类型与 `createCourse()`
- [ ] 建 `src/pages/course-pages.tsx`：`Dashboard`（课程列表）· `NewCourse`（三段表单：课程身份 / 学习任务 / 生成约束）· `CourseWorkspace`（详情占位）
- [ ] `App.tsx` 加路由 `/courses/:slug`；`pages.tsx` 里的内容全部迁到 `course-pages.tsx`
- [ ] 提交成功后 `navigate("/courses/" + course.slug)`
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error；`run build` → 成功
- [ ] 提交：`git commit -m "feat: 前端课程创建向导"`

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

---

### Phase 2 · 持久化事实与 Run 工作台

**阶段目标**：关掉浏览器，Run 还在。把"事实、历史、投影"从页面状态搬进 SQLite。
**进入条件**：Phase 1 全部计划通过。
**退出条件**：Run / Event / Artifact 都落库；刷新页面与重启 API 后读到的内容一致。

#### P2.1 · 建立 SQLite schema 与连接管理

**产出**：13 张表建好，重复初始化不报错。

**文件**
- Create: `apps/api/app/db.py`
- Create: `apps/api/tests/test_database.py`
- Create: `apps/api/tests/conftest.py`

**接口**
- Consumes: P0.2 的 `Settings.database_path`
- Produces: `SCHEMA`（`executescript` 字符串）· `initialize_database(path=None) -> None` · `@contextmanager database() -> Iterator[sqlite3.Connection]` · `row_to_dict(row) -> dict` · `utcnow() -> str`

**步骤**
- [ ] 写 `conftest.py` 的临时库 fixture（每个测试一个独立 `.db` 路径，测试后删除）
- [ ] 写测试：空库调用 `initialize_database()` 后，13 张表全部存在（逐个查 `sqlite_master`）
- [ ] 写测试：**连续调用两次 `initialize_database()` 不抛异常**（迁移幂等）
- [ ] 写测试：`row_to_dict` 把 `payload_json` 解码成 dict 并**去掉 `_json` 后缀**
- [ ] 写测试：`database()` 上下文管理器里抛异常 → 事务回滚（写入的行不存在）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 建立 SQLite schema 与连接管理"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_database.py -v
```

#### P2.2 · 建立 Run 仓储（落账）

**产出**：Run 的每一次状态变化都有可查询的落账。

**文件**
- Create: `apps/api/app/workflow/repository.py`
- Create: `apps/api/tests/test_run_repository.py`

**接口**
- Consumes: P2.1 的 `database()` / `row_to_dict()`
- Produces: `create_run_record(run_id, course_slug, mode, provider, model, request, budget_policy=None) -> dict` · `append_event(run_id, event_type, step, message, payload=None, trace=None) -> dict` · `update_run(run_id, *, status=None, step=None, interrupt_type=None, interrupt_payload=None, error_message=None, clear_interrupt=False, clear_error=False) -> dict` · `record_run_artifact(run_id, step, node, title, presentation, raw_output, source="model") -> dict` · `list_run_artifacts(run_id) -> list[dict]` · `get_run_record(run_id) -> dict` · `list_run_records(course_slug=None) -> list[dict]`

**步骤**
- [ ] 写测试：Run 开始 → 写入 `runs` 一行 + `run_events` 一条「开始」事件
- [ ] 写测试：每阶段写一个 Artifact → `run_artifacts` 有对应行，且 `presentation` 字段完整
- [ ] 写测试：阶段完成 → 追加一条事件
- [ ] 写测试：失败 → 追加一条失败事件 + `runs.error_message` 非空
- [ ] 写测试：`get_run_record(run_id)` 返回 `run` + `events` + `artifacts` + `workflow_steps`（每步 `completed` / `active` / `pending`）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 建立 Run 仓储落账"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_run_repository.py -v
```

#### P2.3 · 建立失败事务与写入幂等

**产出**：写 Artifact 失败时，不会留下"看起来成功"的记录。

**文件**
- Modify: `apps/api/app/workflow/repository.py`
- Modify: `apps/api/tests/test_run_repository.py`

**接口**
- Consumes: P2.2
- Produces: `record_run_artifact()` 在同一事务里写 `run_artifacts` + `artifacts` + `artifact_edges`；重复提交同一 `source`/`node` 不产生重复行

**步骤**
- [ ] 写测试：**故意让 Artifact 写入中途抛异常** → 断言 `run_events` 里没有半截记录、`runs` 状态没被改成成功
- [ ] 写测试：同一 `(run_id, node, source)` 重复写两次 → `run_artifacts` 只有 1 行
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 保证落账的事务性与幂等"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_run_repository.py -v
```

#### P2.4 · 建立工作区与章节乐观并发读写

**产出**：两个人同时改一章，后保存的人拿到 409 而不是静默覆盖。

**文件**
- Modify: `apps/api/app/courses/workspace.py`
- Modify: `apps/api/app/courses/chapters.py`
- Modify: `apps/api/app/api/course_routes.py`
- Create: `apps/api/tests/test_workspace_concurrency.py`

**接口**
- Consumes: P1.4 的 `content_hash` / `_safe_child`；P2.1 的 `chapter_versions`
- Produces: `GET /api/courses/{slug}/chapters/{key}` → `{key, content, content_hash}`；`PUT` 同路径（带 `expected_hash`）；`GET`/`PUT /api/courses/{slug}/workspace/files/{name}`

**步骤**
- [ ] 写测试：读取章节 → 返回非空 `content_hash`
- [ ] 写测试：带**正确** `expected_hash` 保存 → **200**
- [ ] 写测试：带**过期** `expected_hash` 保存 → **409**，且文件内容**未被修改**
- [ ] 写测试：路径穿越（`../../course.json`）→ **4xx**，且课程目录外无任何文件被创建
- [ ] 写测试：覆盖前在 `.agent-history/<ts>/` 建快照
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 工作区与章节乐观并发读写"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workspace_concurrency.py -v
```

#### P2.5 · 暴露 `GET /api/runs` 与完整读模型

**产出**：Run 能被查询到，且读到的内容在重启后不变。

**文件**
- Create: `apps/api/app/api/run_routes.py`
- Create: `apps/api/tests/test_run_api.py`

**接口**
- Consumes: P2.2 的 `get_run_record()`
- Produces: `GET /api/runs` → `{items: [...]}`；`GET /api/runs/{id}` → 完整读模型

**步骤**
- [ ] 写测试：`GET /api/runs/{id}` 返回 `run` / `events` / `artifacts` / `workflow_steps`
- [ ] 写测试：响应**不含**内部绝对路径与模型 Prompt
- [ ] 写测试：未知 `run_id` → **404**
- [ ] 写测试：**重建数据库连接后再读一次，结果与第一次完全相同**（API 重启场景）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 暴露 Run 查询接口"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_run_api.py -v
```

#### P2.6 · 前端：轮询判定 `shouldPollRun`

**产出**：前端知道什么时候该停轮询。

**文件**
- Create: `apps/web/src/features/run/run-polling.ts`
- Create: `apps/web/tests/run-polling.test.ts`

**接口**
- Consumes: P2.5 的 Run 读模型形状
- Produces: `shouldPollRun(run: RunPollingState | undefined): boolean`

**步骤**
- [ ] 写实现：`terminalRunStatuses = new Set(["COMPLETED","FAILED","STOPPED"])`；返回 `!terminalRunStatuses.has(run?.status || "") || Boolean(run?.active_command)`
- [ ] 写测试 4 条：`COMPLETED` 且无活跃命令 → `false`；`FAILED` 且**有**活跃命令 → **`true`**（这是"从检查点继续"的情形，最容易写错）；`RUNNING` → `true`；`undefined` → `true`
- [ ] 跑 `node --experimental-strip-types apps/web/tests/run-polling.test.ts` → PASS
- [ ] 提交：`git commit -m "feat: 增加 Run 轮询判定"`

**验收**
```bash
node --experimental-strip-types apps/web/tests/run-polling.test.ts
```

#### P2.7 · 前端：Run 工作台最小版

**产出**：工作台能看见"跑到哪一步了"和"发生了什么"。

**文件**
- Create: `apps/web/src/features/run/run-workspace.tsx`
- Create: `apps/web/src/features/run/activity.tsx`
- Create: `apps/web/src/features/run/quality-metrics.ts`
- Modify: `apps/web/src/App.tsx`

**接口**
- Consumes: P2.6 的 `shouldPollRun`
- Produces: 路由 `/runs/:runId`；`LiveAgentActivity` · `ElapsedTimer` · `authoritativeEffectiveChars()`

**步骤**
- [ ] 实现 `WorkflowMap`（7 节点横向条，按 `completed`/`active`/`pending` 上色）
- [ ] 实现事件轨：按时间倒序渲染 `events`
- [ ] 实现章节正文只读预览
- [ ] `authoritativeEffectiveChars()` **只读质量快照**，不解析 Artifact（见 §7 补充说明）
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error
- [ ] 提交：`git commit -m "feat: Run 工作台最小版"`

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
# 手工：创建课程 → 刷新页面 → Run 进度与事件仍在
```

#### P2.8 · 从可执行图导出 workflow snapshot

**产出**：拓扑只有一份来源，不再手写第二份。

**文件**
- Create: `apps/api/app/workflow/snapshot.py`
- Create: `apps/api/tests/test_workflow_snapshot.py`

**接口**
- Consumes: P2.1
- Produces: `workflow_snapshot(graph=None) -> dict`（含 `phases`（7 个）· `nodes` · `edges`）

**步骤**
- [ ] 写测试：`phases` 长度精确等于 7，id 与 `STEP_ORDER` 一致
- [ ] 写测试：`nodes` 里的 id 全部来自**可执行图**，不是硬编码常量
- [ ] 写测试：图里加一个测试节点 → snapshot 里**也**出现它（证明是导出的，不是手写的）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: workflow 拓扑从可执行图导出"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workflow_snapshot.py -v
```

---

### Phase 3 · 角色、Skill 与 Artifact

**阶段目标**：把"一个万能 Prompt"拆成 7 个有边界、有 Schema、有权限的角色。
**进入条件**：Phase 2 全部计划通过。
**退出条件**：越权调用被拒；Skill 规则原文进入 Prompt；Artifact 版本不可变。

#### P3.1 · 定义 ModelPolicy 与 AgentDefinition

**产出**：7 个角色的目标、Schema、Skill、工具、模型策略成为可审查的数据。

**文件**
- Create: `apps/api/app/agents/definitions.py`
- Create: `apps/api/tests/test_agent_definitions.py`

**接口**
- Consumes: P1.2
- Produces: `ModelPolicy` · `AgentDefinition` · `MODEL_POLICIES`（5 条：`planning.v1` / `writer.v1` / `review.v1` / `repair.v1` / `presenter.v1`）· `AGENT_DEFINITIONS`（7 条）· `AgentRegistry` Protocol · `TeachingAgentRegistry`

**步骤**
- [ ] 写测试：7 个 agent id 精确等于 `mission.agent` / `research.agent` / `blueprint.agent` / `writer.agent` / `reviewer.agent` / `repair.agent` / `presenter.agent`
- [ ] 写测试：`writer.agent.version == "v1"`、`context_policy_ref == "teaching_skill_packet.v1"`、`model_policy_ref == "writer.v1"`
- [ ] 写测试：每个 agent 的 `model_policy_ref` 都能在 `MODEL_POLICIES` 里找到
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 定义 Agent 契约"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_agent_definitions.py -v
```

#### P3.2 · 实现 TeachingAgentRuntime 与操作白名单

**产出**：角色不能调用别人的能力。

**文件**
- Create: `apps/api/app/agents/executor.py`
- Create: `apps/api/tests/test_agent_tool_runtime.py`

**接口**
- Consumes: P3.1
- Produces: `_OPERATIONS`（按 agent id 的操作集合）· `AgentInvocationDenied(PermissionError)` · `TeachingAgentRuntime(delegate: CourseAgent)`，方法 `definition(agent_id)` 与 `invoke(agent_id, operation, *args, **kwargs)`

**步骤**
- [ ] 写测试：`writer.agent` 可 `generate_chapter`、**不可** `semantic_review` → `AgentInvocationDenied("未声明操作")`
- [ ] 写测试：`reviewer.agent` 可 `semantic_review`、**不可** `apply_repair_patch`
- [ ] 写测试：`invoke` 时 `model_policy_ref` 与当前 agent 不符 → `AgentInvocationDenied`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 角色操作白名单"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_agent_tool_runtime.py -v
```

#### P3.3 · 实现 ToolRuntime 与调用方白名单

**产出**：工具权限**先于副作用**检查。

**文件**
- Create: `apps/api/app/tools/runtime.py`
- Modify: `apps/api/tests/test_agent_tool_runtime.py`

**接口**
- Consumes: P3.1
- Produces: `ToolManifest`（`id` / `callers` / `idempotent` / `description`）· `TOOL_MANIFESTS`（4 条）· `ToolRuntime.execute(tool_id, caller, payload) -> dict` · `ToolInvocationDenied`

**步骤**
- [ ] 写测试：`course.build` 从 `writer.agent` 调用 → `ToolInvocationDenied("{caller} 无权调用 {tool_id}")`
- [ ] 写测试：`course.source_contract` 从 `workflow.generation` 调用 → 放行
- [ ] 写测试：`workspace.patch` 只有 `workflow.planning` 能用
- [ ] 写测试：未注册的工具 → `ToolInvocationDenied("未注册工具：…")`
- [ ] 写测试：**权限检查发生在副作用之前** —— 越权调用后，`workspace/` 里**没有**任何文件被改动
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 受控工具与调用方白名单"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_agent_tool_runtime.py -v
```

#### P3.4 · 建立 ModelTransport 协议与 DeepSeek 实现

**产出**：模型调用是可替换的纯函数层。

**文件**
- Create: `apps/api/app/providers/protocols.py`
- Create: `apps/api/app/provider.py`
- Create: `apps/api/tests/test_provider.py`

**接口**
- Consumes: P3.1
- Produces: `class ModelTransport(Protocol)`（`invoke_text` / `invoke_structured`）· `DeepSeekModelTransport` · `create_model_transport(provider, model=None, settings=None) -> ModelTransport`

**步骤**
- [ ] 写测试：**结构化输出走 `json_mode`**，Prompt 携带 JSON Schema 且明确「不要使用 Markdown 代码围栏」
- [ ] 写测试：空响应**重试一次**，第二次 Prompt 含「上一轮没有返回可解析的 JSON」
- [ ] 写测试：规划类操作 `max_output_tokens == 16384`、超时 600s、**不带** `reasoning_effort`
- [ ] 写测试：`reasoning_effort` 只作用于 `codex_gateway`
- [ ] 写测试：**传输层源码里不含** `teach-generator` / `课程蓝图` / `Humanizer` / `RepairTask`（守住分层）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 建立模型传输层"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_provider.py -v
```

#### P3.5 · 建立 Codex Gateway 传输与模型发现

**产出**：第二个 Provider 可用，且与 DeepSeek 行为一致。

**文件**
- Create: `apps/api/app/providers/gateway.py`
- Modify: `apps/api/app/provider.py`
- Modify: `apps/api/tests/test_provider.py`

**接口**
- Consumes: P3.4 的 `ModelTransport`
- Produces: `CodexGatewayModelTransport` · `CodexGatewayResponsesModel` · `codex_gateway_available() -> bool` · `list_codex_gateway_models() -> list[str]` · `GatewayNoFinalTextError`

**步骤**
- [ ] 写测试：Gateway **无 final text** 时最多尝试 **3 次**
- [ ] 写测试：Gateway 的 `service_tier` 不被模型支持时**不发送该字段**
- [ ] 写测试：**reasoning 文本不得混入 JSON 输出**
- [ ] 写测试：`codex_gateway_available()` 在配置文件不存在时返回 `False`
- [ ] 写测试：章节生成 `max_tokens == 32768`；`humanize` 用 `hard_timeout_seconds == 720`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 接入 Codex Gateway 传输"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_provider.py -v
```

#### P3.6 · 打包 teach-generator Skill 资产进 Prompt

**产出**：Skill 是**规则包**，按角色切片注入，不是复制粘贴。

**文件**
- Create: `apps/api/app/agents/context.py`
- Create: `apps/api/tests/test_agent_context.py`

**接口**
- Consumes: P3.1 的 `context_policy_ref`
- Produces: `_teaching_skill_packet(pedagogy_type: str) -> str`；`_HUMANIZER_PROTOCOL: str`；`_infer_pedagogy(chapter: dict) -> str`

**步骤**
- [ ] 写测试：注入的 Packet 里**逐字包含** Skill 原文中的警告句（「不要照搬本例的 Java 事实」这类）
- [ ] 写测试：不同 `pedagogy_type` 拿到**不同**的资产组合
- [ ] 写测试：Packet 里**不含**整个 SKILL.md（只含当前角色需要的那几段）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 按角色打包 Skill 资产"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_agent_context.py -v
```

#### P3.7 · 实现 Artifact 提交与血缘

**产出**：Artifact 不可变、有版本、有血缘边。

**文件**
- Create: `apps/api/app/workflow/services/artifact_commits.py`
- Create: `apps/api/tests/test_artifact_commits.py`

**接口**
- Consumes: P2.3 的事务能力
- Produces: `commit_chapter_candidate(...) -> dict` · `verify_chapter_candidate(...) -> dict` · `reject_chapter_candidate(...) -> dict`

**步骤**
- [ ] 写测试：提交后内容写到 `.course-agent/artifacts/<run_id>/<artifact_id>/content.md`
- [ ] 写测试：**旧 artifact 被置 `is_current = 0`**，且 `artifact_edges` 记一条 `relation = 'supersedes'`
- [ ] 写测试：**陈旧 `expected_hash` 写入被拒** → 抛并发冲突
- [ ] 写测试：`reject_chapter_candidate()` 之后当前版本回退到上一个
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: Artifact 提交与血缘"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_artifact_commits.py -v
```

#### P3.8 · 补齐 Agent 输出 Schema 与协议方法

**产出**：每个角色的输出都有结构化 Schema，解析失败会**大声失败**。

**文件**
- Modify: `apps/api/app/schemas.py`
- Modify: `apps/api/app/agents/protocols.py`
- Create: `apps/api/tests/test_schemas.py`

**接口**
- Consumes: P3.1
- Produces: `MissionOutput` · `WorkspacePatch` · `BlueprintOutput` · `ModulePlan` · `ChapterPlan`（含 `pedagogy_type` 枚举）· `HumanizerOutput` · `SemanticReviewOutput`（`decision`：`ready` / `manual_review` / `reject`）· `RepairCapabilityPlan`（9 种能力，取 ≤ 4）· `SectionRewriteOutput` · `ContinuityOutput` · `OutputPresentation`

**步骤**
- [ ] 写测试：每个 Schema 的**合法**样例通过、**非法**样例被拒（枚举越界、必填缺失、类型不符）
- [ ] 写测试：`SemanticReviewOutput.decision` 只接受那 3 个值
- [ ] 写测试：`RepairCapabilityPlan` 的能力数量 ≤ 4
- [ ] 写测试：协议补齐到 17 个方法（与 P1.2 的附录一致）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 补齐 Agent 输出 Schema"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_schemas.py -v
```

---

### Phase 4 · Graph、Context 与批次控制

**阶段目标**：把固定顺序的函数串联，换成可路由、可暂停、可恢复的状态图。
**进入条件**：Phase 3 全部计划通过。
**退出条件**：22 节点主图与 4 节点 Review 图可装配；8 个审批点可挂起；批次不跨模块。

#### P4.1 · 定义 CourseAgentState

**产出**：状态里**没有正文**，只有引用与计数。

**文件**
- Create: `apps/api/app/workflow/state.py`
- Create: `apps/api/tests/test_workflow_state.py`

**接口**
- Consumes: P3.8
- Produces: `class CourseAgentState(TypedDict, total=False)`，**46 个字段**

**步骤**
- [ ] 写测试：字段名与类型符合规格（`total=False`）
- [ ] 写测试：字段数量**精确等于 46**
- [ ] 写测试：**断言状态里没有** `mission_text` / `blueprint_markdown` 这类整段正文字段
- [ ] 写测试：`quality_repair_queue` 与 `batch_repair_queue` 是**两个不同**的字段
- [ ] 写测试：`quality_cycle_*` 与 `quality_cycle_no_progress_count` 存在
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 定义图状态"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workflow_state.py -v
```

<details><summary>P4.1.1 · <code>CourseAgentState</code> 的 46 个字段（目标版实测）</summary>

```text
run_id, course_slug, scope, request, feedback, global_change_requests,
workspace_consistency, consistency_retry_count, approval,
mission_markdown, mission_assumptions, workspace_revision,
research, blueprint, batches, current_batch_index, continuity_ledger,
batch_results, retry_count,
quality_repair_queue, quality_repair_active,
batch_repair_queue, batch_repair_active, batch_repair_batch_id,
quality_repair_round, quality_repair_round_results, quality_repair_history,
repair_task_ids, active_repair_task_id, repair_scope, repair_round_summary,
course_quality_report,
quality_cycle, quality_cycle_id, quality_cycle_iteration, quality_cycle_queue,
quality_cycle_attempts, quality_cycle_discovery_sweeps,
quality_refunded_legacy_tasks, quality_cycle_progress_hash, quality_cycle_no_progress_count,
quality_override, review_result, quality_blocked, release_review, final_status
```

> `mission_markdown` / `blueprint` / `batch_results` 里装的是**引用与摘要**，
> 不是整篇正文——正文存在 `run_artifacts` / `artifacts` 表里，靠 `artifact_id` 指回来。
> 这正是 P4.1 那个"状态里没有正文"测试要钉住的不变量。
</details>

#### P4.2 · 实现批次切分 `_make_batches`

**产出**：批次不跨模块、单批不超过 4 章。

**文件**
- Create: `apps/api/app/workflow/services/batch_planning.py`
- Create: `apps/api/tests/test_batch_planning.py`

**接口**
- Consumes: P4.1
- Produces: `_make_batches(blueprint: dict, max_size: int = 4) -> list[dict]`；`_quality_gates_for_result(result) -> dict`；`build_release_review(...) -> dict`

**步骤**
- [ ] 写测试：模块 1 有 5 章 → 切成 `[[1,2,3,4],[5]]`
- [ ] 写测试：批次 id 精确等于 `m1-01-01` 与 `m2-05-05`
- [ ] 写测试：**断言绝不跨模块**（构造一个 7 章单模块 → 切成 4+3，同模块）
- [ ] 写测试：返回项含 `id` / `ordinal` / `display_label` / `module_index` / `module_title` / `chapter_numbers` / `chapter_titles`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现批次切分"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_batch_planning.py -v
```

#### P4.3 · 实现 Context Pack 组装与裁剪

**产出**：每章写作前拿到**有预算**的上下文包。

**文件**
- Create: `apps/api/app/workflow/services/context_packs.py`
- Create: `apps/api/tests/test_context_packs.py`

**接口**
- Consumes: P4.2
- Produces: `_context_pack(state, module, chapter, ledger, feedback="") -> dict`；`_projected(text, limit) -> str`；`_effective_char_count(markdown) -> int`

**步骤**
- [ ] 写测试：落盘到 `courses/<slug>/workspace/context-packs/<batch_id>/chapter-NN.json`
- [ ] 写测试：顶层键**精确**等于 `{schema_version, course_context, module_context, chapter, neighbor_context, continuity_ledger, feedback}`
- [ ] 写测试：相邻章摘要存在
- [ ] 写测试：`RESOURCES.md` 被裁剪到 ≤ 48,000 字符；`COURSE-GENERATION-SPEC.md` ≤ 65,536；`NOTES.md` ≤ 32,000
- [ ] 写测试：continuity ledger 只保留「其他模块最近 2 条 + 同模块最近 8 条」
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现 Context Pack 组装"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_context_packs.py -v
```

#### P4.4 · 实现工作区契约同步与路由判定

**产出**：工作区与蓝图不一致时，**重试**而不是继续。

**文件**
- Create: `apps/api/app/workflow/services/workspace_contract.py`
- Create: `apps/api/tests/test_workspace_contract.py`

**接口**
- Consumes: P4.3
- Produces: `_sync_workspace_contract(state) -> dict`；`_reconciliation_route(state) -> str`；`_workspace_revision_route(state) -> str`

**步骤**
- [ ] 写测试：章节数与 `MISSION.md` 不一致 → `_reconciliation_route` 返回「重试」
- [ ] 写测试：一致 → 返回「继续」
- [ ] 写测试：`_sync_workspace_contract` 把章节数同步进 `COURSE-GENERATION-SPEC.md` 与 `course.json`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 工作区契约同步"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workspace_contract.py -v
```

#### P4.5 · 实现规划节点（mission / blueprint / plan）

**产出**：三个规划节点各自读输入、验输出、写 Artifact、**不决定下一个节点**。

**文件**
- Create: `apps/api/app/workflow/nodes/planning.py`
- Create: `apps/api/tests/test_planning_nodes.py`

**接口**
- Consumes: P4.4
- Produces: 节点函数 `draft_mission` · `revise_workspace` · `reconcile_global_requirements` · `approve_mission` · `research_sources` · `draft_blueprint` · `verify_workspace_contract` · `record_contract_retry` · `approve_blueprint` · `plan_batches` · `approve_plan` + 路由函数 `route_mission` / `route_blueprint` / `route_plan`

**步骤**
- [ ] 写测试：每个节点**返回最小状态更新**（只含 Artifact 引用与计数，不含正文）
- [ ] 写测试：`approve_mission` 的 `APPROVE` / `REVISE` / `STOP` 三条路各有各的目标
- [ ] 写测试：`research_sources` 只发**前 6 个**查询；结果只保留 `http(s)`；按 URL 去重；上限 24
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现规划节点"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_planning_nodes.py -v
```

#### P4.6 · 实现生成节点 `generate_batch`

**产出**：一章正文的完整链路跑通。

**文件**
- Create: `apps/api/app/workflow/nodes/generation.py`
- Create: `apps/api/tests/test_generation_nodes.py`

**接口**
- Consumes: P4.5
- Produces: `generate_batch(state) -> dict`；`route_generated_batch(state) -> str`

**步骤**
- [ ] 写测试：链路顺序精确为 **Writer → 落盘 `lessons/` → Humanizer → 语义审校 → 连续性提取 → Source Contract → 批次构建 → `validate-course`**
- [ ] 写测试：**Humanizer 分数 < 45 时不写 `lessons/`**，而是转修复分支
- [ ] 写测试：`route_generated_batch` 在批次全部通过时返回「下一个批次」
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现生成节点"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_generation_nodes.py -v
```

#### P4.7 · 实现修复与整课质量节点

**产出**：修复队列与整课质量审校各自独立。

**文件**
- Create: `apps/api/app/workflow/nodes/repair.py`
- Create: `apps/api/app/workflow/nodes/quality.py`
- Create: `apps/api/tests/test_repair_quality_nodes.py`

**接口**
- Consumes: P4.6
- Produces: `repair_batch_chapters` · `repair_open_chapters` · `request_batch_review` · `route_quality_repair` · `prepare_course_quality_review` · `course_quality_review` · `route_course_quality`

**步骤**
- [ ] 写测试：修复完成后 `route_quality_repair` 返回「待人工」或「进入整课质量」
- [ ] 写测试：`route_course_quality` 在有未达标章节时返回「修复」，否则返回「发布」
- [ ] 写测试：**质量队列与批次队列不串味**（`batch_repair_queue` 里没有整课修复的项）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现修复与质量节点"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_repair_quality_nodes.py -v
```

#### P4.8 · 实现发布节点与 8 个审批中断

**产出**：8 个人工决策点都能挂起，且能恢复。

**文件**
- Create: `apps/api/app/workflow/nodes/release.py`
- Create: `apps/api/app/workflow/nodes/review.py`
- Create: `apps/api/tests/test_approval_nodes.py`

**接口**
- Consumes: P4.7
- Produces: `prepare_release_review` · `release_approval` · `finalize` · `stop` · `approve_batch`；`interrupt_type` 取值 `MISSION_APPROVAL` · `BLUEPRINT_APPROVAL` · `BATCH_PLAN_APPROVAL` · `BATCH_APPROVAL` · `BATCH_REVIEW_REQUIRED` · `COURSE_QUALITY_REVIEW` · `RELEASE_APPROVAL` · `COURSE_REVIEW_APPROVAL`

**步骤**
- [ ] 写测试：8 个 interrupt 类型**逐一**能被触发，且每个的 `actions` 与当前阶段匹配
- [ ] 写测试：`release_approval` 在 `APPROVE` 且**没有** `release_review` 时抛错
- [ ] 写测试：`stop` 节点把 Run 置 `STOPPED`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 实现发布与审批中断"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_approval_nodes.py -v
```

#### P4.9 · 装配两张可执行图

**产出**：图能跑，节点集合与规格一致。

**文件**
- Create: `apps/api/app/workflow/graph.py`
- Create: `apps/api/app/workflow/assembly/course_graph.py`
- Create: `apps/api/app/workflow/assembly/review_graph.py`
- Create: `apps/api/app/workflow/execution_context.py`
- Create: `apps/api/app/workflow/node_context.py`
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/tests/test_graph_assembly.py`

**接口**
- Consumes: P4.8；P0.1 的 `langgraph` / `langgraph-checkpoint-sqlite`
- Produces: `build_course_graph(run_id, provider, checkpointer) -> CompiledGraph`（**22 个节点**）；`build_review_graph(...)`（**4 个节点**：`inspect` / `approve_review` / `finish` / `stop`）；`app/workflow/graph.py` 作为门面 re-export

**步骤**
- [ ] 写测试：`build_course_graph` 的节点集合**精确等于**附录 P4.9.1 的 22 个 id
- [ ] 写测试：`build_review_graph` 的节点集合精确等于 `["inspect","approve_review","finish","stop"]`
- [ ] 写测试：**条件边是穷尽的**（每个路由函数的返回值都在目标节点集合里，没有"默认继续"）
- [ ] 写测试：装配时传入 `SqliteSaver` checkpointer，检查点落在 `checkpoints.db`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 装配可执行图"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_graph_assembly.py -v
```

<details><summary>P4.9.1 · 主图的 22 个节点与条件边</summary>

```python
NODE_IDS = [
    "draft_mission", "revise_workspace", "reconcile_global_requirements",
    "approve_mission", "research_sources", "draft_blueprint",
    "verify_workspace_contract", "record_contract_retry", "approve_blueprint",
    "plan_batches", "approve_plan", "generate_batch",
    "repair_batch_chapters", "repair_open_chapters", "request_batch_review",
    "approve_batch", "prepare_course_quality_review", "course_quality_review",
    "prepare_release_review", "release_approval", "finalize", "stop",
]
```

| 节点 | 可去的下一个节点 |
| --- | --- |
| `approve_mission` | `revise_workspace` · `draft_mission`(继续) · `stop` |
| `verify_workspace_contract` | `record_contract_retry` · `draft_blueprint` |
| `generate_batch` | `generate_batch`(重试) · `plan_batches`(下一批) · `repair_batch_chapters` · `course_quality_review` · `approve_batch`(人工) |
| `request_batch_review` | `generate_batch`(重试) · `plan_batches`(下一批) · `course_quality_review` · `stop` |
| `repair_batch_chapters` | `repair_batch_chapters`(下一个) · `approve_batch` · `course_quality_review` · `approve_batch`(人工) |
| `course_quality_review` | `repair_open_chapters` · `release_approval` · `stop` |
| `release_approval` | `prepare_release_review`(刷新) · `course_quality_review`(回质量) · `finalize`(发布) |
</details>

---

### Phase 5 · 含 Humanizer 的质量闭环

**阶段目标**：让"生成"变成"生成→审校→修复→再审校"的闭环，并让判定**可复现**。
**进入条件**：Phase 4 全部计划通过。
**退出条件**：质量门能挡住一篇文章；结构与披露契约脚本能独立跑；修复有升级阶梯。

#### P5.1 · 质量 finding 分类与归一化

**产出**：不同来源的失败被归成三类，不会混在一起。

**文件**
- Create: `apps/api/app/quality/findings.py`
- Create: `apps/api/tests/test_quality_findings.py`

**接口**
- Consumes: P3.8 的 `SemanticReviewOutput` / `HumanizerOutput`
- Produces: `class QualityFinding`（`kind` / `severity` / `code` / `message` / `chapter_key` / `source` / `evidence`）；`class QualityFindingKind`（`humanizer` / `semantic` / `deterministic` 三种）；`normalize_humanizer(payload) -> list[QualityFinding]`；`normalize_semantic(payload) -> list[QualityFinding]`；`normalize_deterministic(payload) -> list[QualityFinding]`

**步骤**
- [ ] 写测试：Humanizer 分数 < 45 → 产生一条 `kind == "humanizer"`、`severity == "blocking"` 的 finding
- [ ] 写测试：语义审校 `decision == "manual_review"` → 产生 `severity == "warning"`；`"reject"` → `"blocking"`
- [ ] 写测试：确定性检查失败 → `kind == "deterministic"`
- [ ] 写测试：同一个 `code` 在同一章重复出现 → 归一化后**只保留一条**
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 质量 finding 分类与归一化"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_quality_findings.py -v
```

#### P5.2 · RepairTask 生命周期

**产出**：一次修复有状态、有证据、可重试。

**文件**
- Create: `apps/api/app/quality/repair_tasks.py`
- Create: `apps/api/tests/test_repair_tasks.py`

**接口**
- Consumes: P5.1 的 `QualityFinding`
- Produces: `class RepairTaskStatus`（`open` / `attempting` / `resolved` / `exhausted` / `manual`）；`class RepairTask`；`create_repair_task(findings, chapter_key, course_slug) -> RepairTask`；`record_attempt(task_id, attempt_no, patch, outcome) -> dict`；`resolve_repair_task(task_id, evidence) -> dict`；`exhaust_repair_task(task_id, reason) -> dict`

**步骤**
- [ ] 写测试：新任务初始状态 `open`、`attempts == []`
- [ ] 写测试：`record_attempt` 后状态变 `attempting` 且 `attempts` 长度 1
- [ ] 写测试：`resolve_repair_task` 需要**非空 evidence**，空证据抛错
- [ ] 写测试：`exhaust_repair_task` 后任务**不再**可被 attempt
- [ ] 写测试：任务与 attempt 分别落 `repair_tasks` / `repair_task_attempts` 两张表
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 修复任务生命周期"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_repair_tasks.py -v
```

#### P5.3 · 队列合并与回归检测

**产出**：同一章的多个问题合并成一次扫描；改坏的东西会被发现。

**文件**
- Create: `apps/api/app/quality/queues.py`
- Create: `apps/api/tests/test_quality_queues.py`

**接口**
- Consumes: P5.2 的 `RepairTask`
- Produces: `enqueue_batch_repair(course_slug, batch_id, findings) -> list[RepairTask]`；`enqueue_course_repair(course_slug, findings) -> list[RepairTask]`；`merge_queues(batch_queue, course_queue) -> list[RepairTask]`；`detect_regressions(before, after) -> list[dict]`

**步骤**
- [ ] 写测试：同一章的 3 个 finding → 只产生 **1 个** task
- [ ] 写测试：`merge_queues` 里**批次队列优先**于课程队列
- [ ] 写测试：`detect_regressions` 能识别"修好了一个问题，但引入了另一个新问题"
- [ ] 写测试：修复后 Humanizer 分数**下降** → 判定为回归
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 修复队列合并与回归检测"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_quality_queues.py -v
```

#### P5.4 · 升级阶梯

**产出**：修不好的时候 escalate，而不是无限重试。

**文件**
- Create: `apps/api/app/quality/escalation.py`
- Create: `apps/api/tests/test_quality_escalation.py`

**接口**
- Consumes: P5.3 的 `RepairTask` / `detect_regressions`
- Produces: `class RepairStrategy`（`deterministic` → `llm_patch` → `section_rewrite` → `chapter_rewrite`）；`class RepairStrategyDecision`（`strategy` / `reason` / `needs_manual`）；`decide_strategy(task, attempt_no, regressions) -> RepairStrategyDecision`

**步骤**
- [ ] 写测试：第 1 次尝试 → `deterministic`
- [ ] 写测试：第 2 次尝试 → `llm_patch`
- [ ] 写测试：第 3 次及以后 → `section_rewrite`；再之后 → `chapter_rewrite`
- [ ] 写测试：出现**回归** → 直接跳到 `section_rewrite`（不回到 `llm_patch`）
- [ ] 写测试：达到人工阈值（2 次定向尝试 / 2 轮发现扫描 / 3 轮整课修复）→ `needs_manual == True`
- [ ] 写测试：`llm_patch` 策略下，人工化补丁必须**精确匹配原文**；未命中要报告「1 个 Humanizer 补丁未命中原文，已跳过」
- [ ] 写测试：补丁**不碰代码块**（代码块内部的匹配不生效）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 修复升级阶梯"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_quality_escalation.py -v
```

#### P5.5 · 结构契约脚本（Markdown AST）

**产出**：用真正的 Markdown 解析器判断"结构对不对"，不靠正则。

**文件**
- Create: `scripts/course-structure-contract.mjs`
- Create: `scripts/lib/course-structure-contract.mjs`
- Create: `tests/course-structure-contract.test.mjs`（从占位版扩成真实版）
- Create: `apps/api/tests/test_structure_contract_script.py`

**接口**
- Consumes: P0.4 的 `mdast-util-from-markdown@2.0.3`
- Produces: `analyzeLesson(markdown: string, path = "lesson.md") -> dict`；`analyzeCourse(courseRoot: string, lessonPaths = null) -> dict`；`normalizeReferenceHeading(markdown: string, nodeId: string, expectedHash: string) -> dict`；CLI `scan` / `normalize-reference`（见下方附录 P5.5.1）；4 个诊断码 `TITLE_MISSING` · `INTRO_NON_CANONICAL` · `REFERENCE_SECTION_MISSING` · `EXTERNAL_LINK_BEFORE_REFERENCES`

**步骤**
- [ ] 写 `tests/course-structure-contract.test.mjs`：**每条诊断码至少一条正例 + 一条反例**
- [ ] 写 `test_structure_contract_script.py`：跑 `node scripts/course-structure-contract.mjs scan --course <tmp>`，断言退出码与 JSON 输出形状
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 跑 `npm run test:contract` → 全绿
- [ ] 提交：`git commit -m "feat: 课程结构契约脚本"`

**验收**
```bash
npm run test:contract
node scripts/course-structure-contract.mjs scan --course apps/api/tests/fixtures/valid-course
```

<details><summary>P5.5.1 · 结构契约的诊断码与判定规则</summary>

| 诊断码 | 触发条件 |
| --- | --- |
| `TITLE_MISSING` | 文档没有一级标题，或标题不是文档首块 |
| `INTRO_NON_CANONICAL` | 首个正文块的下一块不是 canonical 引导段 |
| `REFERENCE_SECTION_MISSING` | 没有标题精确为 `参考文献` 的章节 |
| `EXTERNAL_LINK_BEFORE_REFERENCES` | 在 `参考文献` 章节**之前**出现外部链接 |

- **canonical 引导段**：以 `本节` 开头、且包含 `先` 与 `再` 两个字的段落。
- **开放词表候选**：段落长度 ≥ 文档全长的 **45%**、≤ **100 字符**，且其后紧跟一个**至少含 1 个外链**的列表 —— 命中时判 `INTRO_NON_CANONICAL`。
- **canonical 标题**：`参考文献`（允许前后空格）。
- CLI：
  - `node scripts/course-structure-contract.mjs scan --course <root> [--lesson <path> ...]`
  - `node scripts/course-structure-contract.mjs normalize-reference --course <root> --file <file> --node <id> --expected-hash <sha256>`
- 失败时错误以 JSON 打到 **stderr**：`{"error": "..."}`，并 `process.exitCode = 2`。
- `normalize-reference` 是**乐观并发**写：`<expected-hash>` 与当前文件不符时**必须拒绝写入**。
</details>

#### P5.6 · 披露契约脚本

**产出**：把"内部信息不能外泄"变成可执行检查。

**文件**
- Create: `scripts/course-disclosure-contract.mjs`
- Create: `scripts/lib/disclosure-contract.mjs`
- Create: `apps/api/tests/test_disclosure_contract_script.py`

**接口**
- Consumes: P5.5 的 `scripts/lib/` 组织方式
- Produces: `disclosureFindings(content: str) -> list[dict]`（每项含 `label` / `match` / `index`）；`disclosureViolations(content: str) -> list[str]`（只返回标签）；CLI `node scripts/course-disclosure-contract.mjs scan --course <root>`；9 条规则标签（见下方附录 P5.6.1）

**步骤**
- [ ] 写 `test_disclosure_contract_script.py`：9 条规则**各一条正例 + 一条反例**
- [ ] 写测试：**误报边界** —— 「你提供的材料」在引用上下文里**不**算违规
- [ ] 写测试：`disclosureViolations()` 返回**标签数组**，`disclosureFindings()` 返回**带位置的明细**
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 披露契约脚本"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_disclosure_contract_script.py -v
node scripts/course-disclosure-contract.mjs scan --course courses/high-quality-ai-code-review
```

<details><summary>P5.6.1 · 披露契约的 9 条规则（正则逐条钉死）</summary>

| 标签 | 正则 | 命中什么 |
| --- | --- | --- |
| `你提供的材料` | `/(?:基于\|根据\|来自)?你提供的(?:资料\|材料\|内容\|文档\|教程\|资源)/` | 指代用户私有输入的措辞；**"你提供的是 git log 输出"这类练习中的正常对话不命中** |
| `内部材料` | `/内部材料/` | 出现「内部材料」 |
| `蒸馏来源` | `/(?:内容\|资料\|材料)?蒸馏(?:来源\|自\|材料)/` | **"模型蒸馏"是公开技术术语，不命中**；只有描述内部生产来源才命中 |
| `样章流程` | `/样章(?:状态\|验收\|确认\|生成)/` | 内部生产流程词 |
| `内部质检` | `/rubric\s*(?:得分\|分数\|报告\|质检)\|质检报告/i` | 内部质检报告措辞 |
| `Workspace 路径` | `/workspace\//` | 内部目录路径 |
| `内部来源标记` | `/CLAIM-SOURCE/` | 内部来源标记 |
| `等待确认` | `/等待(?:用户)?确认/` | 占位语 |
| `本机路径` | `/(?:Users\|home)\/[A-Za-z0-9._-]+\//` | 本机绝对路径 |

> **第 9 条要按上表实现，不要照抄目标版。**
> 目标版的正则是 `/\/Users\/qi\.qiao/` —— **把某个开发者的用户名写死在了规则里**，
> 换一台机器就完全失效（这正是 §6 缺陷 #14 能溜过检查的原因）。
> 上表的写法对任何用户名都成立，并且额外覆盖 Windows 路径
> （`C:\Users\<name>\` → 统一规范化为 `/Users/<name>/` 之后再匹配）。
</details>

> 第 9 条是目标版**自己违反**的一条：目标仓库的 `quality/phase-1-deterministic.json` 里嵌了
> `/Users/qi.qiao/...`。做这个计划时顺手把目标版的这一处也修掉（见 §6 缺陷 #14）。
</details>

#### P5.7 · 质量快照读写

**产出**：质量结论落在文件里，可以被人读、被机器读、被 diff。

**文件**
- Create: `apps/api/app/quality/snapshot.py`
- Create: `apps/api/tests/test_quality_snapshot.py`

**接口**
- Consumes: P5.1 的 `QualityFinding`；P5.4 的 `RepairStrategyDecision`
- Produces: `write_quality_snapshot(course_slug, run_id, findings, decisions, gates) -> Path`；`read_quality_snapshot(course_slug, run_id) -> dict`；快照落 `courses/<slug>/quality/<run_id>.json`

**步骤**
- [ ] 写测试：快照文件落盘路径正确
- [ ] 写测试：快照内容含 `findings` / `strategies` / `gates` / `effective_chars` / `humanizer_score`
- [ ] 写测试：**同一 `run_id` 重复写** → 覆盖而不是追加
- [ ] 写测试：快照里**不含** Prompt 原文与绝对路径
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 质量快照读写"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_quality_snapshot.py -v
```

#### P5.8 · 前端：批次矩阵与质量面板

**产出**：用户能看见"哪一章卡在哪、为什么"。

**文件**
- Create: `apps/web/src/features/quality/batch-matrix.tsx`
- Create: `apps/web/src/features/quality/quality-panel.tsx`
- Create: `apps/web/src/features/quality/humanizer-score.ts`
- Modify: `apps/web/src/App.tsx`

**接口**
- Consumes: P5.7 的快照形状
- Produces: 组件 `BatchMatrix` · `QualityPanel` · `HumanizerScore`；`readHumanizerScore(snapshot) -> number | null`

**步骤**
- [ ] 写 `humanizer-score.ts`：**只从快照读**，不解析 Artifact 正文（`readHumanizerScore` 返回 `null` 表示未知，**不返回 0**）
- [ ] 实现 `BatchMatrix`：行 = 批次，列 = 章节，格 = 状态色（通过 / 待审 / 失败 / 未跑）
- [ ] 实现 `QualityPanel`：Humanizer 分数 · 有效字符数 · finding 列表（可按 kind 过滤）
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error
- [ ] 提交：`git commit -m "feat: 批次矩阵与质量面板"`

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

---

### Phase 6 · 可恢复执行与人工控制

**阶段目标**：让长时间运行的任务能中断、能续跑、能被人在关键点拍板。
**进入条件**：Phase 5 全部计划通过。
**退出条件**：Worker 独立进程；命令可租约领取；8 个人工点可远程决策；进程被杀后能恢复。

#### P6.1 · 命令队列入队与幂等

**产出**：人工下发的指令进入一个**可靠**的队列。

**文件**
- Create: `apps/api/app/worker/commands.py`
- Create: `apps/api/tests/test_worker_commands.py`

**接口**
- Consumes: P2.1 的 `commands` 表
- Produces: `class CommandKind`（`START` / `RESUME` / `CONTINUE` / `STOP`）；`class CommandStatus`（`pending` / `leased` / `done` / `failed` / `cancelled`）；`enqueue_command(run_id, kind, payload=None, command_id=None) -> dict`；`get_command(command_id) -> dict`；`cancel_command(command_id) -> dict`

**步骤**
- [ ] 写测试：入队后状态 `pending`
- [ ] 写测试：**同一 `command_id` 重复入队 → 幂等**（返回同一条，不新增行）
- [ ] 写测试：`cancel_command` 后 `cancel_requested == 1`
- [ ] 写测试：命令落 `commands` 表，字段齐全
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 命令队列入队"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_worker_commands.py -v
```

#### P6.2 · 租约领取与续租

**产出**：多个 Worker 不会同时做同一件事；死掉的 Worker 的活会被接管。

**文件**
- Modify: `apps/api/app/worker/commands.py`
- Modify: `apps/api/tests/test_worker_commands.py`

**接口**
- Consumes: P6.1
- Produces: `claim_next_command(worker_id, lease_seconds=45) -> dict | None`（用 `BEGIN IMMEDIATE`）；`heartbeat_command(command_id, worker_id) -> dict`；`release_command(command_id, worker_id, status, error=None) -> dict`；`reap_expired_commands(now=None) -> int`

**步骤**
- [ ] 写测试：`claim_next_command` 返回的命令 `leased_by == worker_id` 且 `lease_expires_at` 有值
- [ ] 写测试：**已经租出的命令不会被第二个 Worker 领走**
- [ ] 写测试：`heartbeat_command` 延长 `lease_expires_at`
- [ ] 写测试：租约过期的命令**可以被重新领取**
- [ ] 写测试：`reap_expired_commands` 把过期命令置 `failed`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 租约领取与续租"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_worker_commands.py -v
```

#### P6.3 · 节点级幂等 claim

**产出**：同一个节点跑第二次时，不会重复扣预算、不会重复写文件。

**文件**
- Create: `apps/api/app/worker/node_claims.py`
- Create: `apps/api/tests/test_node_claims.py`

**接口**
- Consumes: P2.1 的 `node_executions` 表
- Produces: `class ClaimStatus`（`claimed` / `reused` / `busy`）；`claim_node(run_id, node_id, input_hash) -> ClaimStatus`；`complete_node(run_id, node_id, input_hash, result_ref) -> None`

**步骤**
- [ ] 写测试：第一次 claim → `claimed`
- [ ] 写测试：**同 `input_hash` 第二次 claim → `reused`**
- [ ] 写测试：不同 `input_hash` 且前一个未完成 → `busy`
- [ ] 写测试：`complete_node` 后可以再次 `claim`（新的 input_hash）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 节点级幂等 claim"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_node_claims.py -v
```

#### P6.4 · WorkflowRuntime 与检查点续跑

**产出**：图能跑；跑到一半杀进程，再起来能接着跑。

**文件**
- Create: `apps/api/app/workflow/runtime.py`
- Create: `apps/api/tests/test_workflow_runtime.py`

**接口**
- Consumes: P4.9 的两张图；P6.3 的 claim；P2.2 的仓储
- Produces: `class WorkflowRuntime`：`start(run_id, request) -> dict` · `resume(run_id, command) -> dict` · `continue_after_interrupt(run_id, action, payload) -> dict` · `stop(run_id) -> dict` · `status(run_id) -> dict`；检查点落 `checkpoints.db`

**步骤**
- [ ] 写测试：`start` 走到第一个 interrupt 就**停下来**，返回 `interrupt_type == "MISSION_APPROVAL"`
- [ ] 写测试：`continue_after_interrupt(run_id, "APPROVE")` 继续跑到下一个 interrupt
- [ ] 写测试：同一个 `run_id` 第二次 `start` → **不重复跑**已完成的节点（`node_executions` 命中 `reused`）
- [ ] 写测试：**模拟进程死亡** —— 跑到一半直接抛异常，再 `resume` → 从检查点继续，不重跑已完成节点
- [ ] 写测试：`stop` 之后 Run 状态为 `STOPPED`，且后续 `resume` 无效
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 工作流运行时与检查点续跑"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workflow_runtime.py -v
```

#### P6.5 · Worker 独立进程

**产出**：长任务在独立进程里跑，不占着 API。

**文件**
- Create: `apps/api/app/worker/main.py`
- Create: `apps/api/tests/test_worker_main.py`

**接口**
- Consumes: P6.2 的 `claim_next_command` / P6.4 的 `WorkflowRuntime`
- Produces: `apps/api/app/worker/main.py`（入口 `python -m app.worker.main`）；`WorkerLoop(worker_id, poll_interval=2.0)`；`run_forever()` / `run_once() -> bool`

**步骤**
- [ ] 写测试：`run_once()` 在队列为空时返回 `False`（没有可领的活）
- [ ] 写测试：`run_once()` 领到命令后返回 `True`，且命令状态变 `done`
- [ ] 写测试：Worker **不监听任何 HTTP 端口**
- [ ] 写测试：命令执行抛异常 → 命令置 `failed` 且 Worker **不崩**
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: Worker 独立进程"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_worker_main.py -v
cd apps/api && .venv/bin/python -m app.worker.main --once
```

#### P6.6 · 暴露 resolve / continue / stop / SSE

**产出**：人可以远程拍板。

**文件**
- Create: `apps/api/app/api/control_routes.py`
- Create: `apps/api/tests/test_control_api.py`

**接口**
- Consumes: P6.4 的 `WorkflowRuntime`
- Produces: `POST /api/runs/{id}/resolve`（body `{action, payload}`）→ 200 · `POST /api/runs/{id}/continue` → 200 · `POST /api/runs/{id}/stop` → 200 · `GET /api/runs/{id}/events`（**SSE**）

**步骤**
- [ ] 写测试：`resolve` 带非法 action → **422**
- [ ] 写测试：`resolve` 在 Run 不处于 interrupt 状态 → **409**
- [ ] 写测试：`resolve` 在 `RELEASE_APPROVAL` 阶段但**没有** `release_review` → **409**「整课总结尚未生成」，且**不产生空的发布记录**（§7 失败模式 #5 的路由侧）
- [ ] 写测试：`stop` 后 Run 为 `STOPPED`
- [ ] 写测试：SSE 端点**立刻**吐出已有事件，然后保持连接
- [ ] 写测试：SSE 的 `Content-Type` 是 `text/event-stream`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 人工控制与 SSE"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_control_api.py -v
curl -N http://127.0.0.1:8000/api/runs/<run_id>/events
```

#### P6.7 · 启动脚本三进程 + Provider 校验

**产出**：一条命令拉起 API + Worker + Vite，并在凭据缺失时**早失败**。

**文件**
- Modify: `scripts/start-agent.sh`（脚手架已有两进程版本：API + Vite；扩成三进程）
- Modify: `apps/api/app/config.py`

**接口**
- Consumes: P0.3 的 `.env.example`；P6.5 的 Worker 入口
- Produces: `scripts/start-agent.sh`（子命令 `api` / `worker` / `web` / `all` / `check`）；`check_provider_available() -> tuple[bool, str]`

**步骤**
- [ ] 写 `check_provider_available()`：Gateway 配置缺失 → 返回 `(False, "未找到 ~/.codex/config.toml")`
- [ ] 写测试：**DeepSeek 模式下缺 `DEEPSEEK_API_KEY` → 同样返回 False**，并说明缺哪个变量
- [ ] 写 `scripts/start-agent.sh`：`check` 子命令只做校验；`all` 并行拉起三个进程
- [ ] `start-agent.sh` 里 **绝不能** 出现 `~/.codex/config.toml` 里的 token
- [ ] 跑 `bash scripts/start-agent.sh check` → 打印明确结论
- [ ] 提交：`git commit -m "feat: 三进程启动脚本与凭据校验"`

**验收**
```bash
bash scripts/start-agent.sh check
grep -rn "token" scripts/start-agent.sh    # 不得出现真实 token
```

#### P6.8 · 前端：执行面板与审批按钮矩阵

**产出**：审批按钮和后端的 action 集合**逐条对齐**。

**文件**
- Create: `apps/web/src/features/execution/execution-panel.tsx`
- Create: `apps/web/src/features/execution/approval-actions.ts`
- Create: `apps/web/src/features/execution/decision-bar.tsx`
- Create: `apps/web/tests/approval-actions.test.ts`
- Modify: `apps/web/src/App.tsx`

**接口**
- Consumes: P6.6 的控制路由
- Produces: `approvalActionsFor(stage: string): Action[]`（按钮矩阵，见下方附录 P6.8.1）；组件 `ExecutionPanel` · `DecisionBar`

**步骤**
- [ ] 写 `approval-actions.test.ts`：**8 个 interrupt 类型逐一断言按钮集合**（这是最容易写错的表）
- [ ] 写测试：`release` 阶段**额外**有 `STOP` 按钮
- [ ] 写测试：非法 stage → 返回**空数组**（不抛错）
- [ ] 写测试：`resolve` 返回 **409**（例如"整课总结尚未生成"）→ UI **回滚乐观更新**并显示错误，**不得**静默失败（§7 失败模式 #5 的前端侧）
- [ ] 跑 `node --experimental-strip-types apps/web/tests/approval-actions.test.ts` → PASS
- [ ] 实现 `ExecutionPanel`：显示当前 Run 状态、当前 interrupt、可点按钮
- [ ] 实现 `DecisionBar`：点按钮 → 调 `resolve` → 乐观更新 UI → 失败时回滚并提示
- [ ] 提交：`git commit -m "feat: 执行面板与审批按钮"`

**验收**
```bash
node --experimental-strip-types apps/web/tests/approval-actions.test.ts
npm --prefix apps/web run typecheck
```

<details><summary>P6.8.1 · 审批按钮矩阵</summary>

| 阶段 / interrupt | `APPROVE` | `REVISE` | `STOP` | 其他 |
| --- | --- | --- | --- | --- |
| `MISSION_APPROVAL` | ✅ | ✅ | ✅ | — |
| `BLUEPRINT_APPROVAL` | ✅ | ✅ | ✅ | — |
| `BATCH_PLAN_APPROVAL` | ✅ | ✅ | ✅ | — |
| `BATCH_APPROVAL` | ✅ | ✅ | ✅ | — |
| `BATCH_REVIEW_REQUIRED` | ✅ | ✅ | ✅ | — |
| `COURSE_QUALITY_REVIEW` | ✅ | ✅ | ✅ | — |
| `RELEASE_APPROVAL` | ✅ | ✅ | ✅ | 额外 `REGENERATE_SUMMARY` |
| `COURSE_REVIEW_APPROVAL` | ✅ | ✅ | ✅ | — |

- 任何阶段都**不得**出现 `REGENERATE_SUMMARY` 以外的第四种 action。
- `action` 的取值域固定为：`APPROVE` / `REVISE` / `STOP` / `REGENERATE_SUMMARY`。
</details>

---

### Phase 7 · 可观测性与交付治理

**阶段目标**：能回答"钱花在哪、卡在哪、谁改的"。
**进入条件**：Phase 6 全部计划通过。
**退出条件**：Trace 与预算可查；Provider 设置可改且密钥不外泄；僵死 Run 能自愈。

#### P7.1 · Trace 上下文与 span

**产出**：一次 Run 的所有调用串成一条可折叠的链路。

**文件**
- Create: `apps/api/app/observability/trace.py`
- Create: `apps/api/tests/test_trace.py`

**接口**
- Consumes: P2.1 的 `trace_spans` 表
- Produces: `class SpanContext`（`trace_id` / `span_id` / `parent_span_id` / `name` / `started_at` / `ended_at` / `attributes`）；`start_span(trace_id, name, parent_span_id=None, attributes=None) -> SpanContext`；`end_span(span, attributes=None) -> dict`；`list_spans(trace_id) -> list[dict]`

**步骤**
- [ ] 写测试：`trace_id` **恒等于** `run_id`（不另生成）
- [ ] 写测试：span 有父子关系，`list_spans` 按 `started_at` 排序
- [ ] 写测试：未结束的 span 不出现在"已完成"查询里
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: Trace 上下文与 span"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_trace.py -v
```

#### P7.2 · 属性白名单与 Trace 投影

**产出**：Trace 里**不会有**不该落库的东西。

**文件**
- Modify: `apps/api/app/observability/trace.py`
- Create: `apps/api/tests/test_trace_redaction.py`

**接口**
- Consumes: P7.1
- Produces: `ALLOWED_SPAN_ATTRIBUTES`（白名单集合）；`project_attributes(attributes) -> dict`（丢弃白名单外的键）

**步骤**
- [ ] 写测试：`api_key` / `token` / `authorization` / `prompt` / `secret` 等键**被丢弃**
- [ ] 写测试：白名单内的键（如 `node_id` / `duration_ms` / `chapter_key`）**被保留**
- [ ] 写测试：白名单**不存在时**默认丢弃一切（fail-closed）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: Trace 属性白名单"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_trace_redaction.py -v
```

#### P7.3 · 预算账本与投影

**产出**：Token 与成本有账，超阈值只提醒一次。

**文件**
- Create: `apps/api/app/observability/budget.py`
- Create: `apps/api/tests/test_budget.py`

**接口**
- Consumes: P2.1 的 `budget_ledger_entries` / `budget_adjustments`
- Produces: `class BudgetScope`（`run` / `course` / `agent` / `node`）；`record_usage(scope, scope_id, tokens_in, tokens_out, cost_usd=None, model=None) -> dict`；`project_budget(run_id) -> dict`（`used` / `limit` / `remaining` / `by_agent`）；`adjust_budget(run_id, delta_mtokens, reason) -> dict`；`check_budget(run_id) -> dict`

**步骤**
- [ ] 写测试：累计用量后 `project_budget` 的 `used` 等于各条之和
- [ ] 写测试：超过 `limit` → `check_budget` 返回 `over_budget == True`
- [ ] 写测试：**超阈值事件只发一次**（重复调用 `check_budget` 不会重复发事件）
- [ ] 写测试：`adjust_budget` 抬高上限后 `over_budget` 变 `False`
- [ ] 写测试：调整记录落 `budget_adjustments`
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 预算账本与投影"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_budget.py -v
```

#### P7.4 · 暴露 `GET /api/workflow`

**产出**：前端能画出真实的图，而不是硬编码的示意图。

**文件**
- Create: `apps/api/app/api/workflow_routes.py`
- Modify: `apps/api/app/api/router.py`
- Create: `apps/api/tests/test_workflow_api.py`

**接口**
- Consumes: P2.8 的 `workflow_snapshot()`
- Produces: `GET /api/workflow` → `{phases, nodes, edges}`

**步骤**
- [ ] 写测试：响应含 `phases`（7 个）· `nodes`（含 22 个主图节点）· `edges`
- [ ] 写测试：每条 edge 的 `source` / `target` 都能在 `nodes` 里找到（**不悬空**）
- [ ] 写测试：节点带 `phase` 字段，值在 7 个 phase id 里
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 暴露工作流拓扑接口"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_workflow_api.py -v
curl http://127.0.0.1:8000/api/workflow
```

#### P7.5 · 暴露 `PUT /api/settings/provider`

**产出**：能在 UI 里切 Provider，密钥**永不**回落到前端。

**文件**
- Create: `apps/api/app/api/settings_routes.py`
- Create: `apps/api/tests/test_settings_api.py`

**接口**
- Consumes: P0.2 的 `get_provider_preferences()` / `save_provider_preferences()`
- Produces: `PUT /api/settings/provider`（body `{provider, model}`）→ 200；`GET /api/settings/provider` → `{provider, model, available: bool}`（**无密钥字段**）

**步骤**
- [ ] 写测试：`GET` 响应**不含** `api_key` / `token` / `secret` 任意一个（逐个 key 断言）
- [ ] 写测试：`PUT` 合法 → 200，且新设置**持久化**（重新读 `<repo_root>/.course-agent/provider-settings.json` 确认）
- [ ] 写测试：`PUT` 非法 provider → **422**
- [ ] 写测试：**仓库里不出现**真实密钥（`git grep` 无命中）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: Provider 设置接口"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_settings_api.py -v
```

#### P7.6 · 僵死 Run 恢复

**产出**：Worker 崩了之后，Run 不会永远卡在 `RUNNING`。

**文件**
- Modify: `apps/api/app/worker/commands.py`
- Modify: `apps/api/app/api/run_routes.py`
- Create: `apps/api/tests/test_stale_runs.py`

**接口**
- Consumes: P6.2 的租约字段
- Produces: `reap_stale_runs(older_than_seconds=300) -> list[str]`（返回被标记的 run_id）；`GET /api/runs` 里 `RUNNING` 但超时的 Run 显示为 `FAILED`

**步骤**
- [ ] 写测试：构造一个 `RUNNING` 且 `heartbeat_at` 是 10 分钟前的 Run → 被标记 `FAILED`，并写一条失败事件
- [ ] 写测试：心跳新鲜的 Run **不被**动
- [ ] 写测试：恢复动作**幂等**（跑两次结果一致）
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 僵死 Run 恢复"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_stale_runs.py -v
```

#### P7.7 · 前端：Trace 与预算面板

**产出**：能看到调用链与预算消耗。

**文件**
- Create: `apps/web/src/features/observability/trace-panel.tsx`
- Create: `apps/web/src/features/observability/budget-panel.tsx`
- Create: `apps/web/src/features/observability/span-tree.tsx`
- Modify: `apps/web/src/App.tsx`

**接口**
- Consumes: P7.3 的 `project_budget` 形状；P7.1 的 span 列表
- Produces: 组件 `TracePanel` · `BudgetPanel` · `SpanTree`

**步骤**
- [ ] 实现 `SpanTree`：按 `parent_span_id` 折叠成树，**默认只展开根**
- [ ] 实现 `BudgetPanel`：已用 / 上限 / 剩余 + 按 agent 的条形分布；超限时明确标红
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error
- [ ] 提交：`git commit -m "feat: Trace 与预算面板"`

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

#### P7.8 · 前端：编排图与样式层

**产出**：工作台能画出真实的 22 节点图，视觉上是一套系统。

**文件**
- Create: `apps/web/src/features/workflow/graph-view.tsx`
- Create: `apps/web/src/features/workflow/graph-data.ts`
- Create: `apps/web/src/styles/base.css`
- Create: `apps/web/src/styles/workbench.css`
- Create: `apps/web/src/styles/responsive.css`
- Modify: `apps/web/src/styles.css`

**接口**
- Consumes: P7.4 的 `/api/workflow`
- Produces: 组件 `GraphView`（`@xyflow/react`）；`graph-data.ts::toFlowElements(snapshot)`；12 个样式文件（分层见下方附录 P7.8.1）

**步骤**
- [ ] 写 `toFlowElements`：把 `{phases, nodes, edges}` 转成 React Flow 的 `{nodes, edges}`，**边不悬空**
- [ ] 实现 `GraphView`：`nodes` 按 phase 着色；`edges` 带条件标签；点击节点高亮其上游
- [ ] 按附录 P7.8.1 拆分 12 个样式文件，`styles.css` 只做 import 汇总
- [ ] 跑 `npm --prefix apps/web run typecheck` → 0 error
- [ ] 跑 `node scripts/check-source-size.mjs` → 每个文件 ≤ 500 行
- [ ] 提交：`git commit -m "feat: 编排图与样式分层"`

**验收**
```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
node scripts/check-source-size.mjs
```

<details><summary>P7.8.1 · 12 个样式文件的分层与体量</summary>

| 文件 | 职责 | 约计行数 |
| --- | --- | --- |
| `styles/base.css` | reset + 变量 + 排版基线 | ~416 |
| `styles/workbench.css` | 工作台布局 | ~388 |
| `styles/responsive.css` | 断点适配 | ~226 |
| `styles/studio.css` | 工作室主视觉 | ~490 |
| `styles/studio-workflow.css` | 工作室工作流 | ~369 |
| `styles/studio-responsive.css` | 工作室响应式 | ~152 |
| `styles/studio-canvas.css` | 画布 | ~197 |
| `styles/studio-typography.css` | 字体层级 | ~349 |
| `styles/budget-observability.css` | 预算与可观测性 | ~6 |
| `styles/button-states.css` | 按钮状态 | ~15 |
| `styles/index.css` | import 清单 | ~11 |
| `styles.css`（根） | shim，只 re-export `index.css` | 极短 |

> 每个文件都必须在 500 行门内（`scripts/check-source-size.mjs` 会拦）。
> `budget-observability.css` 只有 6 行是**故意的** —— 预算相关样式并入工作台层，避免无谓的文件碎片。
>
> **导入顺序敏感**：`index.css` 的导入清单必须是
> `base → workbench → responsive → studio → studio-workflow → studio-responsive → studio-canvas → studio-typography → budget-observability → button-states → @xyflow/react/dist/style.css`。
> `studio*.css` 覆盖 `base.css` / `workbench.css`；`@xyflow/react/dist/style.css` **必须最后导入**。
</details>

---

### Phase 8 · 交付收敛

**阶段目标**：把"能跑"变成"能交付"：静态站点可发布、契约测试全绿、文档可读、证据齐全。
**进入条件**：Phase 7 全部计划通过。
**退出条件**：§5 的全部验收命令跑过；仓库里没有一处"未跑过"的证据。

#### P8.1 · 静态课程构建脚本（12 步）

**产出**：Markdown 课程 → 静态 HTML 站点，**确定性**重建。

**文件**
- Create: `scripts/build-static-course.mjs`
- Create: `scripts/lib/build-pipeline.mjs`
- Create: `scripts/lib/lesson-renderer.mjs`
- Create: `apps/api/tests/test_build_static_course.py`

**接口**
- Consumes: P5.5 的结构契约；P5.6 的披露契约
- Produces: `node scripts/build-static-course.mjs --course <root> --out <dir>`；12 步流水线（见下方附录 P8.1.1）

**步骤**
- [ ] 写 `test_build_static_course.py`：用最小样例课程跑一遍，断言产物目录含 `index.html` + 每章一个 HTML
- [ ] 写测试：**同样的输入跑两次 → 输出逐字节相同**（确定性）
- [ ] 写测试：章节 Markdown → HTML 时，标题层级、代码块、表格、列表都正确
- [ ] 写测试：**结构契约不通过 → 构建失败并给出诊断码**
- [ ] 写测试：**披露契约不通过 → 构建失败**
- [ ] 跑测试 → FAIL → 实现 → PASS
- [ ] 提交：`git commit -m "feat: 静态课程构建脚本"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_build_static_course.py -v
node scripts/build-static-course.mjs --course apps/api/tests/fixtures/valid-course --out /tmp/out
```

<details><summary>P8.1.1 · 12 步构建流水线</summary>

| # | 步骤 | 说明 |
| --- | --- | --- |
| 1 | 扫描课程目录 | 读 `course.json` / `lessons/` / `reference/` |
| 2 | 读取结构契约 | 调 `scripts/lib/structure-contract.mjs` |
| 3 | 读取披露契约 | 调 `scripts/lib/disclosure-contract.mjs` |
| 4 | 章节排序 | 按 `course.json` 的 `modules` / `lessons` 顺序 |
| 5 | Markdown → HTML | 标题 / 代码块 / 表格 / 列表 / 引用 |
| 6 | 提取章节摘要 | 用于首页与导航 |
| 7 | 生成导航 | 目录树 + 上一页 / 下一页 |
| 8 | 注入资产 | `assets/` 下的图片与附件 |
| 9 | 复制静态资源 | ⚠️ 见下方说明 |
| 10 | 生成 `index.html` | 课程首页 |
| 11 | 写入 `catalog.json` | 课程索引 |
| 12 | 自检 | 链接可达、无空文件、章节数与 `course.json` 一致 |

> ⚠️ **第 9 步是目标版的已知缺陷**（§6 缺陷 #13）：目标版从
> `courses/high-quality-ai-code-review/assets/` 复制资源，而**这个目录在两棵树里都不存在**，
> `copyFileSync` 会抛 `ENOENT`，脚本根本跑不起来。
> **本计划必须修掉它**：改成"assets 目录存在才复制，不存在则跳过并记一条 warning"，
> 并为这条分支补一个测试。
</details>

#### P8.2 · 根级契约测试补齐 10 条

**产出**：`npm run test:contract` 覆盖发布契约的 10 个面。

**文件**
- Modify: `tests/course-structure-contract.test.mjs`
- Create: `tests/course-disclosure-contract.test.mjs`
- Create: `tests/course-build-contract.test.mjs`

**接口**
- Consumes: P5.5 / P5.6 / P8.1 的脚本
- Produces: 10 条契约测试（清单见下方附录 P8.2.1）

**步骤**
- [ ] 把 P5.5 的占位版测试扩成完整版
- [ ] 按附录 P8.2.1 逐条写测试（每条测试**先写反例**）
- [ ] 跑 `npm run test:contract` → 10 条全绿
- [ ] 提交：`git commit -m "test: 补齐根级契约测试"`

**验收**
```bash
npm run test:contract
```

<details><summary>P8.2.1 · 10 条根级契约测试</summary>

1. 每篇课程 Markdown 都有唯一的一级标题
2. 引导段是 canonical 形式（`本节…先…再…`）
3. 每篇都有 `参考文献` 章节
4. `参考文献` 之前没有外链
5. 正文不含本机路径（`/Users/…`、`/home/…`、`C:\Users\…`）
6. 正文不含内部流程词（内部材料 / 内部质检 / 蒸馏来源 / 样章流程 / 等待确认）
7. 章节数与 `course.json` 的 `lessons` 一致
8. 每章都有非空正文（有效字符数 > 0）
9. 静态构建产物包含全部章节且链接可达
10. `catalog.json` 的每条都能在课程目录里找到
</details>

#### P8.3 · 补齐样例课程 `workspace/` 与 `quality/`

**产出**：仓库里有一门**完整的**样例课程，Review 图能读它。

**文件**
- Create: `courses/high-quality-ai-code-review/workspace/NOTES.md`
- Create: `courses/high-quality-ai-code-review/workspace/RESOURCES.md`
- Create: `courses/high-quality-ai-code-review/workspace/COURSE-GENERATION-SPEC.md`
- Create: `courses/high-quality-ai-code-review/quality/phase-1-deterministic.json`
- Create: `apps/api/tests/test_sample_course.py`

**接口**
- Consumes: P2.8 的 Review 图输入；P5.6 的披露契约
- Produces: 样例课程的 workspace 三件套 + 质量快照

**步骤**
- [ ] 写 `test_sample_course.py`：三件套都存在，且**都不超过裁剪上限**（48,000 / 65,536 / 32,000）
- [ ] 写测试：质量快照能被 `read_quality_snapshot` 读出来
- [ ] 写测试：样例课程**不触发**披露契约的 `本机路径` 规则（这条正是目标版踩的坑，见 §6 缺陷 #14）
- [ ] 跑测试 → FAIL → 写内容 → PASS
- [ ] 提交：`git commit -m "feat: 补齐样例课程工作区与质量快照"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_sample_course.py -v
node scripts/course-disclosure-contract.mjs scan --course courses/high-quality-ai-code-review
```

#### P8.4 · 补回 `course.json` 发布元数据

**产出**：课程元数据完整到能直接发布。

**文件**
- Modify: `courses/high-quality-ai-code-review/course.json`
- Create: `apps/api/tests/test_course_publication.py`

**接口**
- Consumes: P1.5 的 `course.json` 结构
- Produces: `course.json` 含 `slug` · `title` · `audience` · `goals` · `scope` · `publication`（`title` / `description` / `language` / `published_at` / `href`）· `modules`（每模块 `id` / `title` / `summary` / `lessons`）· `lessons` · `status`

**步骤**
- [ ] 写 `test_course_publication.py`：`publication.href` 存在且**不是**绝对本机路径
- [ ] 写测试：`modules` 的 `lessons` 数量之和 == 顶层 `lessons` 数量
- [ ] 写测试：`course.json` 能被 `json.loads` 且通过 Pydantic 模型校验
- [ ] 跑测试 → FAIL → 补内容 → PASS
- [ ] 提交：`git commit -m "feat: 补回课程发布元数据"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests/test_course_publication.py -v
```

#### P8.5 · 修失效测试 + 补 `response_model`

**产出**：目标版遗留的 4 条失效测试全部转绿；API 响应有 Schema。

**文件**
- Modify: `apps/api/app/api/course_routes.py`
- Modify: `apps/api/app/api/run_routes.py`
- Modify: `apps/api/tests/`（4 条失效测试）
- Create: `apps/api/tests/test_response_models.py`

**接口**
- Consumes: P3.8 的 Schema
- Produces: 每个路由声明 `response_model=`；`test_response_models.py` 断言响应字段与 Schema 一致

**步骤**
- [ ] 写 `test_response_models.py`：**故意返回多余字段** → 被 `response_model` 过滤掉
- [ ] 跑 `pytest apps/api/tests` → 记录**当前失败**的 4 条（目标版遗留）
- [ ] 逐条修：修**测试的错误断言**，不改产品行为（除非断言本身反映了一个真 bug，那就修产品并在提交信息里写清）
- [ ] 给 `course_routes` / `run_routes` 的每个路由补 `response_model`
- [ ] 跑 `pytest apps/api/tests` → **0 failed**
- [ ] 提交：`git commit -m "fix: 修复失效测试并补齐响应模型"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests -v
```

#### P8.6 · 截图与 README / AGENTS 改写

**产出**：新克隆的人打开仓库就知道怎么跑起来。

**文件**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Create: `docs/screenshots/`
- Modify: `implementation-guide-20-lessons/README.md`（加"与本路线图的关系"一节）

**接口**
- Consumes: P6.7 的 `scripts/start-agent.sh`
- Produces: README 含 5 段：**它是什么** / **架构图** / **快速开始**（3 条命令）/ **目录结构** / **阶段进度表**；`docs/screenshots/` 至少 3 张

**步骤**
- [ ] 重写 README：删掉"这是教学脚手架"的说法，改成**成品系统**的说明书
- [ ] README 里加一张架构图（Mermaid）与一张七阶段流程图
- [ ] 加"快速开始"：`bash scripts/start-agent.sh check` → `bash scripts/start-agent.sh all` → 打开 `http://localhost:5173`
- [ ] 改写 `AGENTS.md`：**删掉**"本仓库是教学子集、不含后端运行时"这类过时描述，改成**真实**的目录职责与开发约定
- [ ] 用真实运行结果截 3 张图放进 `docs/screenshots/`（**必须是真图**，不许用占位图）
- [ ] 在 `implementation-guide-20-lessons/README.md` 加一节说明"本路线图与教学指南的关系"
- [ ] 提交：`git commit -m "docs: 改写 README 与 AGENTS 并补截图"`

**验收**
```bash
# 逐条按 README 的"快速开始"从零跑一遍，三条命令都能跑通
bash scripts/start-agent.sh check && bash scripts/start-agent.sh all
```

#### P8.7 · 全量验收与阶段证据

**产出**：§5 的每一条验收命令都**真的跑过**，并留下证据。

**文件**
- Modify: `implementation-guide-20-lessons/templates/stage-evidence.md`
- Create: `docs/acceptance/`

**接口**
- Consumes: §5 的全部命令
- Produces: `docs/acceptance/<phase>.md`（每个阶段一份：命令、真实输出摘要、结论）

**步骤**
- [ ] 逐条跑 §5 的**全部**验收命令，**把真实输出**贴进 `docs/acceptance/`
- [ ] 任何一条失败 → **先修再继续**，不许写「已知问题」了事
- [ ] 跑 `pytest apps/api/tests -v` → 统计 passed / skipped，写进证据
- [ ] 跑 `npm run test:contract` → 10 条全绿，写进证据
- [ ] 跑 `node scripts/check-source-size.mjs` → 通过，写进证据
- [ ] 跑 `npm --prefix apps/web run typecheck && npm --prefix apps/web run build` → 通过，写进证据
- [ ] 填 `stage-evidence.md`：每阶段的**日期**、**命令**、**真实输出**、**结论**；没有跑过的一律写 `NOT RUN` + 原因
- [ ] 提交：`git commit -m "chore: 记录全量验收证据"`

**验收**
```bash
apps/api/.venv/bin/python -m pytest apps/api/tests -v
npm run test:contract
node scripts/check-source-size.mjs
npm --prefix apps/web run typecheck && npm --prefix apps/web run build
```

> **本计划是唯一一个"不产生新功能"的计划** —— 它产生的是**证据**。
> 没有证据，前面 69 个计划的"完成"全部只是声明。

---

## 4. 全局约束

**所有里程碑都适用，逐字执行。**

### 4.1 代码规范

| 约束 | 精确值 |
| --- | --- |
| Python 版本 | `>=3.12`（3.12 / 3.13 / 3.14 均可；`requires-python` **不得**写成 `>=3.12,<3.13`） |
| 虚拟环境解释器路径 | Linux / macOS：`apps/api/.venv/bin/python`；Windows：`apps\api\.venv\Scripts\python.exe`。本文所有 `apps/api/.venv/bin/python` 形式的验收命令，在 Windows 上按此替换 |
| Ruff | `line-length = 92`，`target-version = "py312"`，默认规则集（E4/E7/E9/F） |
| 单文件行数上限 | **500 行**；扫描范围**精确为** `apps/api/app` + `apps/web/src`，扩展名**精确为** `.py / .ts / .tsx / .css`；测试目录、`scripts/`、`tests/`、`.mjs/.js/.json/.md` 不受此门禁约束 |
| 单行最大长度 | 92 字符（Python） |
| 前端 | React 19 + TypeScript 5.9，**不引入**组件库（无 shadcn / Radix / Tailwind / MUI） |
| API 契约变更 | 必须同步更新 `apps/web/src/api.ts` 的类型 + 对应测试 |
| 路由组织 | 公开响应使用明确返回类型或 `response_model` |
| 规模门必须双入口 | `node scripts/check-source-size.mjs` **和** `pytest apps/api/tests/test_source_size.py` 都要能跑，且都绿 |

> ⚠️ 目标版的 API 层**没有任何 `response_model=`**（响应全是裸 `dict`），这与本仓库
> `AGENTS.md` 的既有规范冲突。**建议在 M2 就补上 `response_model`**，
> 否则 OpenAPI 里没有响应 schema，前端只能靠手写 TS 类型对齐。

### 4.2 领域不变量（任何里程碑都不得破坏）

1. 七阶段 id 与顺序固定；`release` 必须保留人工决策权，模型和代码不得静默替代该决定。
2. `release` 阶段的 `APPROVE` 必须要求已存在 `release_review`，避免空摘要被误发布。
3. 课程正文事实源是 `courses/<slug>/lessons/*.md`；HTML 是可重建的发布产物；
   数据库和聊天记录**都不是**正文事实源。
4. 所有文件读写限定在 `courses/<slug>/` 内；路径必须规范化并做越界校验。
5. Workspace 与章节保存必须基于内容 hash 的乐观并发；覆盖前建立可恢复快照。
6. 模型不得执行无限制 Shell、访问仓库外路径或直接发布到公网。
7. 密钥（`DEEPSEEK_API_KEY` / Codex token）不落仓库、不回传前端读模型。
8. `.venv/` · `node_modules/` · `.course-agent/` · `.pytest_cache/` · `apps/api/.env` 不提交。
9. **工具权限必须先于副作用检查**——无权调用时要**先拒绝**，再谈有没有产生副作用。
   （Stage 03 的硬约束：Writer 请求 publish 工具必须在副作用发生前被拒。）
10. **Graph 状态不携带正文**——`CourseAgentState` 里只有 Artifact 引用、批次指针、
    审批状态和有限循环计数；**不得**出现 `mission_text` / `blueprint_markdown` 这类
    整段正文字段。（Stage 04 的硬约束。）

### 4.3 验收纪律（继承自 `implementation-guide-20-lessons/`）

这套纪律是本仓库既有文档的明确要求，本路线图不得削弱它：

1. **三层验收，缺一不可** ——
   ① **自动化关**：规定的测试 / typecheck / build / 专项脚本**实际执行过**，且你知道结果是什么；
   ② **学员验收步骤**：从 M2 起，每个里程碑必须**额外**完成一个失败、重复、降级或恢复场景；
   ③ **解释关**：你能用自己的话说明"事实存在哪里、谁有控制权、失败如何收敛、证据放在哪里"。
2. **永远不要写"应该通过"。** 命令有没有运行、实际输出是什么、被什么挡住了、
   截图、API 响应、Run ID、Artifact 版本、日志关联信息——都如实写进
   `implementation-guide-20-lessons/templates/stage-evidence.md`。
   `NOT RUN` 必须写明真实的环境原因。
3. **Agent 的完成声明不是证据。** 你亲手跑出来的结果才是。
4. **核心验收必须能用 Fake Provider 复现。** 真实模型调用可以用来冒烟测试，
   但不能是唯一验收路径——否则验收结果不可重复。
5. **不静默改变领域契约。** API 与领域对象的语义、状态转换与人工决策的含义、
   Artifact / Snapshot / Event / Checkpoint 的职责、重复/失败/恢复/质量/发布的可观察行为，
   这些可以换实现，**不能换含义**。

### 4.4 依赖钉死（照抄，不要用 `^` 改写运行时版本）

```
fastapi==0.139.2          httpx==0.28.1
langchain==1.3.14         langchain-deepseek==1.1.0
langgraph==1.2.9          langgraph-checkpoint-sqlite==3.1.0
pydantic==2.13.4          pydantic-settings==2.13.1
uvicorn[standard]==0.41.0 pytest==8.4.2  ruff==0.12.11
```

前端新增：`@tanstack/react-query@5.101.2` · `@xyflow/react@^12.11.2` ·
`framer-motion@12.38.0` · `lucide-react@0.468.0` · `mermaid@^11.16.0` ·
`react-markdown@10.1.0` · `react-syntax-highlighter@^16.1.1` · `remark-gfm@4.0.1`

---

## 5. 最终验收矩阵

到达 Phase 8（M8）时，下列命令必须**全部实际执行过**，并把真实输出记入阶段证据
（收尾动作是 **P8.7 全量验收与阶段证据**）：

| 命令 | 期望 | 归属计划 |
| --- | --- | --- |
| `apps/api/.venv/bin/python -m pytest apps/api/tests` | 全绿（目标版 160 条 / 3,300 行） | **P8.7** |
| `apps/api/.venv/bin/ruff check apps/api` | `All checks passed` | 全程 |
| `npm --prefix apps/web run typecheck` | 0 error | 全程 |
| `npm --prefix apps/web run build` | 成功产出 `dist/` | 全程 |
| `npm run test:contract` | 契约测试全绿 | **P8.2** |
| `npm run check:source-size` | `Source size check passed` | **P0.5** 引入，全程 |
| `node scripts/build-static-course.mjs advanced-learning-of-obsidian` | 重建 HTML 成功 | **P8.1** |
| `node .agents/skills/teach-generator/scripts/validate-course.mjs courses/advanced-learning-of-obsidian` | 课程校验通过 | **P8.1** |
| `bash scripts/start-agent.sh` | API + Worker + Vite 三进程起来 | **P6.7** |
| `curl /api/health` | `status:"ok"` + provider 状态 | **P1.7** |
| `curl /api/courses` | 返回已发布课程 + `resumable_run_id` | **P1.6** |
| `curl /api/workflow` | 7 phase + 节点 + agents + tools | **P7.4** |
| 手工：正常路径 | 创建 → 批准 → 生成 → 质量 → 发布 | **P6.4** |
| 手工：恢复路径 | Worker 中途被杀 → 重启后从 checkpoint 继续 | **P6.4** · **P6.5** |
| 手工：人工路径 | 挂起 → 要求修改 → 带反馈继续 | **P6.6** · **P6.8** |

---

## 6. 目标版本已知缺陷（实现时建议直接修掉，不要照抄）

这些是**目标版 `main` 分支现存的问题**，照抄会一起带进你的新仓库：

| # | 问题 | 位置 | 建议 |
| --- | --- | --- | --- |
| 1 | **4 条测试指向已裁剪的课程**，在目标树上直接失败 | `test_course_service.py`（3 条）· `test_artifact_service.py`（1 条） | 改指 `advanced-learning-of-obsidian`（9 章，`lessons/01-rag.md`…`09-agentic.md`） |
| 2 | **拓扑双真相**：`workflow/snapshot.py` 是手写的第二份拓扑，已与真实图漂移 | `snapshot.py:57-59` 明确写着 `approve_batch` "has no incoming edge" | 让 snapshot 从编译后的图导出；或加一条测试断言两边节点集合一致 |
| 3 | **无 `response_model`** | `app/api/*` 全部路由 | M2 起补 `response_model` |
| 4 | **预算策略无法从 HTTP 修改** | `PUT /api/runs/{id}/budget` 被测试断言为 405 | 加一条 `PUT` 路由或在文档里说明"只能在创建时设定" |
| 5 | **`@types/react-syntax-highlighter` 误放在 `dependencies`** | `apps/web/package.json` | 移到 `devDependencies` |
| 6 | **前端没有 `test` 脚本** | `apps/web/package.json` | 加 `"test": "node --experimental-strip-types tests/run-polling.test.ts"` |
| 7 | **每个 `.tsx` 顶部 49 行重复且大多未使用的 import** | `apps/web/src/**` | 清理；或抽一个 `ui/kit.ts` 统一导出 |
| 8 | **`humanizer-zh/SKILL.md` 未在运行时被读取**，协议内联在 `agents/context.py:252` | `agents/context.py` | 改成从 Skill 文件读取，让 Skill 真正成为可版本化的规则源 |
| 9 | **`catalog.json` 与 API 课程列表是两个独立来源** | `catalog.list_courses()` 从不读 `catalog.json` | 明确 catalog.json 仅是发布索引；或在测试里断言两者一致 |
| 10 | **死代码** | `run_routes._workflow_scope` 从未被调用 | 删除 |
| 11 | **PPMondwest 字体走远程 URL** | `base.css` 的 `@font-face` | 自托管字体，或改用系统字体栈 |
| 12 | **`agents/course_runtime.py::_invoke_with_hard_timeout` 是空壳** | 该函数直接 `return callback()` | 真正超时在 `provider.py` 里；两处语义重复，容易误改 |
| 13 | 🔴 **`build-static-course.mjs` 在目标仓库里根本跑不起来** | 第 9 步从 `courses/high-quality-ai-code-review/assets/` 复制主题资源，但**该目录在两个仓库里都不存在** → `copyFileSync` 抛 `ENOENT` | **建仓第一天就会撞上**。要么新建最小模板课程目录，要么让复制步骤在模板缺失时跳过并沿用课程自己的 `assets/`（见 **P8.1.1** 第 9 步） |
| 14 | 🔴 **目标版自己的已提交产物违反了自己的披露规则** | `quality/phase-1-deterministic.json` 内嵌 `courseRoot` / `repositoryRoot` = `/Users/qi.qiao/Documents/Playground/...`，正是「本机路径」规则禁止的内容（规则只作用于学生可见文件，`quality/` 不在校验根里，所以没被抓到） | 生成 `phase-1-deterministic.json` 时把绝对路径换成仓库相对路径 |
| 15 | **`markdown/course-01-00.md` 是 0 字节残留** | 某次没有章节匹配上的构建留下的（`padStart(2,"0")` 把 0 补成了 "00"） | 构建时若最后一章号不存在，**不要**写合并文件；并清掉这个残留文件 |
| 16 | **Command 类型与教学指引不一致** | 指引写 `START / STOP / RESUME / REVISE`，目标版实现的是 `START / RESUME / CONTINUE / STOP` | 明确 `REVISE`（人工修订）与 `CONTINUE`（从失败检查点重放）是两回事，并把这个差异写进技术方案 |
| 17 | **lockfile 的去留没有结论** | 目标版 `package-lock.json` 与 `apps/web/package-lock.json` 都是**未跟踪**状态，且历史上有两个提交（`abc7a9f`、`9b4ceb9`）**故意删掉**过 lockfile；根 lockfile 里还有 `node_modules/ai-course-studio-tools` 的自引用残留 | **主动决定**：要么提交 lockfile（可复现安装，删掉自引用条目），要么继续不提交并在 README 写明原因。不要留着"看起来是意外"的状态 |
| 18 | **`validate-course.mjs` 跨目录 import 根级脚本** | `.agents/skills/teach-generator/scripts/validate-course.mjs` 依赖 `../../../../scripts/lib/course-structure-contract.mjs` | Skill 依赖仓库根脚本，**根脚本一旦移动 Skill 就断**。要么把契约库下沉到 `.agents/skills/teach-generator/` 内（根脚本反向 import 它），要么在 README 里把这个耦合写清楚 |

---

## 7. Review Focus：最容易咬人的五个失败模式

这些是规格**暗示但没有明说**、而一旦出错最伤人的地方。
每个都**已经落到某个具体计划的某一步**上——右列给出钉住它的计划 ID 与测试位置：

| # | 失败模式 | 合理预期 | 钉住它的计划 | 目标版测试名 |
| --- | --- | --- | --- | --- |
| 1 | Workspace 文件保存时路径穿越（`../../course.json`） | 返回 4xx，**绝不**写到课程目录外 | **P2.4** · `test_workspace_concurrency.py` | `test_course_service.py::test_workspace_rejects_path_traversal` |
| 2 | 两个编辑器同时改一章，后保存者静默覆盖 | 返回 409，UI 提示"刷新并比较"，不静默丢内容 | **P2.4**（读）/ **P3.7**（写）· `expected_hash` 机制 | `test_artifact_service.py` |
| 3 | Worker 租约过期后被另一 Worker 抢占，同一节点跑两遍 | 同 `(run_id, node_id, input_hash)` 只执行一次；重复调用返回 `reused` | **P6.2**（租约）+ **P6.3**（幂等） | `test_command_worker.py` |
| 4 | Humanizer 分数 44（或语义 `decision != ready`）的章节被放进 `lessons/` 当成成品 | 不得放行；必须生成带证据的 RepairTask | **P4.6**（拦）+ **P5.2**（落任务） | `test_quality_cycle.py` |
| 5 | `release` 阶段在没有 `release_review` 的情况下被批准发布 | 返回 409「整课总结尚未生成」，不产生空的发布记录 | **P4.8**（节点）+ **P6.6**（路由） | `test_api_contract.py` |

> **第 5 条最容易被漏掉**：它在后端是"节点直接抛错"，在前端是"按钮点下去之后
> 必须把错误显示出来，而不是静默失败"。两侧都要有测试——`P4.8` 测节点，
> `P6.8` 测 UI 的失败回滚。

> 补充一条规格留白但工程上必须处理的：**质量结论有两个来源**——
> `quality/course-quality-snapshot.json`（原子写入的当前事实）和
> `quality/agent-batch-*.json`（批次历史）。目标版选择"快照为准、Artifact 仅作迁移兜底"，
> 前端 `chapterQualityMap()` 也是这个规则。**请保持同一规则**，否则工作台会显示互相矛盾的数字。

---

## 8. 依赖图

### 8.1 阶段级（9 个阶段严格串行）

```text
Phase 0 工程底座
 │
 ▼
Phase 1 七步 Happy Path V0 ───────────┐
 │                                    │  内存态可演示
 ▼                                    │
Phase 2 持久化事实 + Run 工作台 ───────┤  刷新/重启不丢
 │                                    │
 ▼                                    │
Phase 3 角色 + Artifact + 工具权限 ─────┤  可审查的边界
 │                                    │
 ▼                                    │
Phase 4 Graph + Context + 批次 ────────┤  可路由的状态图
 │                                    │
 ▼                                    │
Phase 5 质量闭环 + 修复 ───────────────┤  有证据的质量
 │                                    │
 ▼                                    │
Phase 6 Worker + 人工控制 ─────────────┤  可恢复的执行
 │                                    │
 ▼                                    │
Phase 7 可观测性 + 交付治理 ────────────┤  可证明的完成
 │                                    │
 ▼                                    │
Phase 8 交付收敛 ◄─────────────────────┘  打开就能演示
```

### 8.2 计划级：跨阶段的关键依赖边

阶段是串行的，但**跨阶段存在几条"可以提前做"的边**——提前做能省掉返工：

```text
P0.4 根 package.json ──────────────► P5.5 结构契约脚本
   │                                     │
   └─► P0.5 规模门 ───► P8.2 契约测试    └─► P5.6 披露契约
                                              │
                                              └─► P8.1 静态构建 ──► P8.2 契约测试

P2.1 SQLite schema ──► P6.1 命令队列 ──► P6.2 租约 ──► P6.3 节点幂等
                            │                              │
                            └──────────────────────────────┴──► P6.4 WorkflowRuntime
                                                                        │
                            P3.7 Artifact 提交 ────────────────────────┤
                                                                        ▼
P4.9 装配两张图 ──────────────────────────────────────────────► P6.4
                                                                        │
                                                                        ▼
                                                              P6.5 Worker
                                                              P6.6 人工控制
                                                                        │
                                                                        ▼
                                                              P8.7 全量验收
```

**被 plan ID 钉住的四条硬依赖**（违反其一，后面必然返工）：

| 边 | 违反后果 |
| --- | --- |
| `P2.1` → `P2.4` → `P2.5` | 章节乐观并发没有落库依据，409 退化成静默覆盖 |
| `P3.3`（工具白名单）→ `P4.5`/`P4.6`（节点） | 节点直接调工具，权限边界形同虚设 |
| `P4.3`（Context Pack）→ `P4.6`（生成节点） | 写作没有裁剪后的上下文，上下文成本不可控 |
| `P6.3`（节点幂等）→ `P6.4`（续跑） | 恢复时重复扣预算、重复写文件 |

### 8.3 并行可能性（如果多人协作）

| 可并行的两件事 | 条件 |
| --- | --- |
| `P0.4`（根脚本）∥ `P0.1`（Python 依赖） | 无依赖 |
| `P1.8` / `P2.7` / `P5.8` / `P6.8` / `P7.7`（前端各面板） | 各自只依赖同阶段的后端计划，不互相依赖 |
| `P7.7`（Trace/预算面板）∥ `P7.8`（编排图与样式层） | 样式层只有 `P7.8` 用 |
| `P8.3`（样例课程数据）∥ `P8.1`（静态构建） | 两者都只读 Phase 2–5 已定下的落盘格式 |
| `P0.4` + `P5.5`（契约脚本）提前到 Phase 1 之前 | 契约早于实现，能提前锁住发布格式 |

---

## 9. 与既有实施指引的关系

| 文件 | 负责什么 | 与本文件的关系 |
| --- | --- | --- |
| `implementation-guide-20-lessons/00-…07-*.md` | **怎么学**：阅读地图、分步任务、三类提示词（规划 / 实施 / 排障）、人类 Review 清单、验收关卡、解释关 | 本文件的**每个 Phase 对应其中一个阶段**，提供该阶段的工程答案 |
| `implementation-guide-20-lessons/teaching-scaffold-implementation.md` | **脚手架是怎么来的**：完整 Demo → 薄脚手架的裁剪映射 | 本文件是**它的逆向映射**：薄脚手架 → 完整 Demo |
| `assets/aiagent/PRD.md` · `BE-TD.md` · `FE-TD.md` | **要做什么**：产品目标、领域语义、API 契约、UI 结构 | 本文件的所有数字与契约都从这里来 |
| `RoadMap.md`（本文件） | **建什么**：文件清单、接口签名、阶段与计划顺序、验收命令 | 与实施指引并行阅读；§3 的 70 个计划是它的**可执行化** |

### 9.1 两者怎么配合用

| 场景 | 读哪个 |
| --- | --- |
| 第一次接触这套系统 | 先读 `implementation-guide-20-lessons/README.md` 的八阶段总览，再读本文件 §1 + §2 |
| **领一个任务去做** | 本文件 §3 的 `#### Pn.k` 小节 —— 它自带全部决定，不需要再翻别的文档 |
| 想知道"这一步为什么这么设计" | 对应阶段的 `implementation-guide-20-lessons/0N-*.md` |
| 卡住了要排障 | `implementation-guide-20-lessons/` 里的**排障提示词**那一节 |
| 准备交付 | 本文件 §5 验收矩阵 + §4 全局约束 |

> **两边的粒度不同是刻意的。** 教学指引按"人一次学一个概念"组织，
> 本文件按"一次能独立完成一个任务"组织。教学指引的阶段 03 可能横跨本文件的
> `P3.1`–`P3.8` 八个计划；反过来，一个计划也可能横跨教学指引里的两个小节。
> **以本文件的 Plan ID 为准**——它是提交、评审和验收的最小单位。

---

*基准版本：目标仓库 `main` @ `9628ff2`（含 `608881d feat: 完整可交付课程版本` 的完整工程形态）。*
*本文档中的行数、文件数、测试数、以及 §6 的每一条缺陷，均已在两个仓库上实测复核（2026-10-26）。*
