# 阶段 02：把 V0 变成可追溯的事实与工作台

**预计投入：** 6 至 10 小时。

**一句话目标：** 用 SQLite、Pydantic、FastAPI 与 React Query 让 V0 的结果在刷新页面和重启 API 之后仍然可查询、可追溯。

**这不是终态：** 事实已经落账，但角色、Graph、质量循环和执行恢复都还没有完成。你的系统现在能记住发生了什么，但还不知道怎么安全地继续。

## 你将完成什么

阶段 01 的 V0 跑起来的时候，一切都是新鲜的。但如果你刷新页面或者重启 API，所有东西就消失了——Runner 的状态在内存里，Markdown 可能只在响应对象里，进度条是唯一的记录。这个阶段要解决的就是这个问题。

完成之后，用户创建一次课程生产请求，系统会持久化一个 `Course` 作为课程的长期身份，持久化一个 `Run` 作为一次固定输入下的生产尝试，持久化原始的 `Intake` 作为用户提交的意图，持久化关键输出 `Artifact` 作为可引用、可版本化的内容产物，追加不可变的 `Event` 作为"发生过什么"的历史记录，生成可读取的 `Snapshot` 作为给页面的当前投影，并保留课程的 Workspace 位置。刷新页面之后你仍然能看到同一个 Run，API 重启之后你仍然能查询到它，你能看到当前阶段和最后的结果，也能看到失败的摘要。从这一刻起，你不会再把页面内存当成事实了。

## 你现在站在哪里

阶段 01 的 V0 已经跑通了完整形状，但它有一个根本性的问题：Runner 把状态放在内存字典里，结果只在响应对象中存在，Markdown 没有版本，进度条是唯一的记录。一旦刷新、重启或重新打开页面，系统就彻底失忆。这不只是体验问题——它让错误难以复盘，让重复请求难以判断，让后续的 Worker 无法安全接管。本阶段用一组明确的事实对象来替换 V0 的临时记忆，让每一次运行、每一个产物、每一段历史都有迹可循。

## 本阶段替换什么问题

V0 的便利做法是"Runner 返回一个大对象"，前端拿到渲染，结束。一旦刷新或重启，什么都没了。本阶段把 Runner 内部的那个大对象拆成七个各有寿命和权限的事实：

| 对象 | 职责 | 寿命 | 可变性 |
| --- | --- | --- | --- |
| Course | 课程的长期身份与工作空间归属 | 创建后持续存在 | 基本属性可修改 |
| Run | 一次固定输入下的生产尝试 | 单次执行周期 | 状态随执行推进 |
| Intake | 用户提交的原始意图 | 不可变 | 不可变 |
| Artifact | 可引用、可版本化的内容产物 | 创建后保留所有版本 | 追加新版本，不覆盖旧版本 |
| Event | 发生过什么的不可变历史 | 不可变 | 不可变，只追加 |
| Snapshot | 给页面读取的当前投影 | 每次状态变化时重建 | 可覆盖 |
| Workspace | 课程文件的受控目录位置 | 归属 Course | 文件随 Run 增删 |

这些对象不能用一个 JSON Blob 偷偷代替。如果你现在用一个万能字段存所有东西，后面的角色不知道自己的输入 Artifact 在哪里，Graph 不知道状态应该引用什么，质量 Finding 不知道应该关联哪个版本，Worker 不知道崩溃后应该从哪个 checkpoint 恢复。事实层的设计是之后五个阶段的共同基础。

## 两份 Skill 在本阶段的角色

`teach-generator` 要求任务定义、来源、蓝图、笔记和课程文件有清楚的位置。因此 Workspace 不能只是随手生成的临时目录——它必须归属于 Course，必须与某一次 Run 的执行区分开。`humanizer-zh` 在这一阶段仍然只是未来质量 Gate 的规则来源，不要提前把它的规则扫描结果写成最终质量结论。你可以为将来的 Quality Artifact 预留命名方式，但不要为了"通用"而把未来所有质量表都建出来。

## 学习导航

### 本阶段必读

阅读第 04 章的请求链，理解前后端的数据流动。阅读第 05 章的领域对象与 API 契约，这是本阶段最核心的参考——它告诉你 Course、Run、Artifact 这些对象应该怎么设计。阅读第 05 章的同步异步边界，虽然 V0 还跑在同步模式，但你需要知道异步执行会在什么时候变得必要。阅读第 06 章的 SQLite 表设计，学习如何用迁移管理表结构。阅读第 06 章的全栈 Agent 架构，理解各层之间的数据归属。阅读第 19 章的对象契约，再次确认 V0 最终要交付的对象长什么样。

### 实施时查阅

查阅第 12 章的持久执行，理解 Command 和 Worker 如何与持久化事实配合。查阅第 15 章的读模型和可观测事实，理解 Snapshot 和读取投影的设计原则。查阅第 18 章的 Trace 与边界，为后续的可观测性做准备。

### 完成后回看

回看第 08 章的 Artifact，重新理解什么是可审查的产物。回看第 16 章的 Command 与 Worker，为阶段 06 的执行权交接做准备。

### Demo 阅读地图

阅读 `apps/api/app/workflow/repository.py` 的持久化职责，阅读 `apps/api/app/workflow/command_repository.py` 的命令事实，阅读 `apps/api/app/db.py` 的业务库与 checkpoint 库边界，阅读 `apps/api/app/schemas.py` 的输入输出模型，阅读 `apps/web/src/api.ts` 的查询调用，阅读 `apps/web/src/pages/course-pages.tsx` 的读取投影。不要复制现有完整表结构，不要把 Demo 的历史兼容逻辑带入学习项目——你的表结构应该只服务于当前阶段的需求。

## 五类边界

| 范围 | 本阶段要做 | 本阶段不做 | 理由 |
| --- | --- | --- | --- |
| 前端 | Run 工作台、刷新查询、错误状态 | 复杂编辑器与审批中心 | 先让事实可读，再考虑编辑 |
| 后端 | Course/Run/Artifact/Event/Snapshot API | 角色编排 API | 先稳定数据契约 |
| 数据 | SQLite 最小表、迁移、Workspace 归属 | 全量质量与执行表 | 避免预建终态，按需扩展 |
| 运行时 | V0 Runner 写入事实和投影 | Worker、lease、恢复 | 执行权后置到阶段 06 |
| 测试 | 重启、刷新、重复与写入失败 | 双 Worker 竞争 | 当前风险是事实丢失 |

## 事实图

```text
Course ---- owns ----> Workspace
  |
  +---- has many ----> Run
                         |
                         +---- records ----> Intake
                         +---- appends ----> Event
                         +---- produces ---> Artifact(version)
                         +---- projects ---> Snapshot

React Workbench ---- reads ----> Snapshot + selected Artifacts
```

这张图里有几条关键关系值得单独说清楚：Course 不等于某一次 Run——一个 Course 可以有多次 Run，每次 Run 有独立的输入和结果。Run 不等于页面 Tab——页面只是一个观察窗口，Run 的事实存在数据库里。Artifact 不等于 Event 文案——Event 是"Mission 已生成"，Artifact 是 Mission 的完整内容。Snapshot 不等于唯一事实——它是投影，方便页面读取，但真相永远在 Event 和 Artifact 里。Workspace 文件不等于数据库中的当前状态——文件是产物的一种存放形式，数据库是事实的源头。

## 分步任务

### 任务 1：写出对象词典

为 Course、Run、Intake、Artifact、Event、Snapshot、Workspace 七个对象各写一句职责。为每个对象写稳定 ID、创建者、是否可变、页面是否直接读取。完成定义是没有"万能 run_data"字段把所有东西混在一起。证据是对象词典和 Schema 草图。

### 任务 2：设计最小 SQLite 表

先从 Course、Run、Intake、Artifact、Event、Snapshot 开始，只增加当前 V0 需要的字段。Artifact 要有类型、版本、内容位置与来源 Run，Event 要有时间、类型、关联 Run 与摘要，Snapshot 要可重建或明确标注为投影。完成定义是迁移可以重复执行——删掉数据库再跑迁移，结果一致。证据是空库建表测试。

### 任务 3：让 V0 Runner 落账

这是本阶段最核心的任务。Run 开始时写 Intake 与开始 Event；Mission、Blueprint、Batch plan、Lesson 和质量摘要各写成一个 Artifact；每个阶段完成时追加一个 Event；阶段结束时更新 Snapshot；失败时写失败 Event 与失败 Snapshot。完成定义是 Runner 的返回值不再是唯一证据——你关掉 Runner，打开 SQLite，依然能看到完整的运行历史。证据是 SQLite 查询结果。

### 任务 4：实现读取 API

提供 Course 的列表或单 Course 读取，提供单 Run 的 Snapshot 读取，提供 Artifact 列表和单版本读取。响应模型不暴露内部路径和敏感 Prompt。完成定义是刷新页面后能恢复——前端拿到 run_id 就能从 API 拿到完整的当前状态。证据是重启 API 后的请求响应。

### 任务 5：实现最小 Run 工作台

让 React Query 管理远端读取状态，让页面用 `run_id` 查询 Snapshot。加载时显示加载状态，失败时显示可重试的读取错误，空 Artifact 时显示"事实尚未产生"而不是空白页面。完成定义是页面不依赖 V0 Runner 的内存——Runner 可以已经不存在了，但页面仍然能展示上一次 Run 的结果。证据是硬刷新截图。

### 任务 6：写失败事务测试

模拟 Artifact 写入失败，确认不会生成假的成功 Snapshot。模拟重复提交，确认语义明确且不会覆盖旧 Artifact。模拟 API 重启，确认读取结果仍一致。证据是测试和数据库检查。这些测试保护的是你之后五个阶段的数据完整性——如果现在的事实层可以被悄悄破坏，后面所有的质量、恢复和治理都建立在沙子上。


## 关于对象设计的补充说明

在动手写代码之前，有几点设计决策值得单独说清楚，因为它们会影响你后面好几个阶段的实现。

**Course 和 Run 的关系。** 一个 Course 可以有多次 Run。为什么？因为用户可能想用不同的输入参数重新生成课程，也可能在第一次 Run 失败后重新开始。如果你把 Course 和 Run 合并成一个对象，你就无法区分"这门课的身份"和"这次生成的结果"。Course 的 ID 是稳定的，Run 的 ID 是每次创建时新生成的。这个区分在阶段 06 引入 Worker 之后会变得特别重要——Worker 需要知道自己在为哪个 Run 工作，而页面需要知道自己在展示哪个 Course 的哪次 Run。

**Artifact 的版本策略。** 本阶段只需要最简单的版本管理——每个 Artifact 有一个版本号，新版本写入时不覆盖旧版本。你不需要实现完整的 Git 式分支和合并。但你需要确保：Artifact 的 ID 是稳定的，版本号是递增的，旧版本在数据库中仍然可读。这个简单策略在阶段 05 引入 Candidate 和修复闭环时会自然扩展，不需要在本阶段过度设计。

**Snapshot 的更新时机。** Snapshot 是给页面快速读取的投影，它应该在每次 Run 状态变化时更新，而不是在页面请求时才计算。为什么？因为计算 Snapshot 可能需要联表查询多个 Event 和 Artifact，如果每次页面刷新都做一次，会不必要地增加 API 负载。更好的做法是：Runner 在每次阶段完成时更新 Snapshot，API 只读取已计算好的 Snapshot。这样前端查询始终是 O(1) 的。

**Workspace 的目录结构。** teach-generator 对 workspace 有明确的要求。Course 的 workspace 目录应该在 Course 创建时初始化，而不是在第一次 Run 时。目录结构可以简单到 `workspace/{course_slug}/`，里面包含 MISSION.md、RESOURCES.md、COURSE-BLUEPRINT.md 等文件。这些文件是课程生产的持久化产物，不是某一次 Run 的临时文件。Run 的产物应该放在 Run 的子目录下，与 Course 级别的文件分开。

### 关于测试策略的说明

本阶段的测试有两个重点。第一是迁移的可重复性——删掉数据库再跑迁移，结果应该完全一致，这是你之后所有数据变更的安全网。第二是事务失败后的状态一致性——如果 Artifact 写入失败，Snapshot 不应该被更新为成功状态；如果 Event 写入失败，不应该有对应的"已完成"Snapshot。这些测试不是为了证明"你的代码能跑"，而是为了证明"你的代码在失败时不会悄悄产生不一致的事实"。这种"失败路径测试"会在后续每个阶段变得越来越重要——阶段 05 的质量闭环、阶段 06 的 Worker 恢复、阶段 07 的交付证据，都依赖于你现在建立的事实层完整性。

## 提示词

复制下面这段提示词发给你的 Coding Agent。它会先分析当前系统状态和设计方案，再按顺序逐一实现。

```text
你正在一个包含两份 Skill、设计文档、AGENTS.md 和七步完整实现的学习仓库中工作。当前 Run 的状态保存在内存中，刷新或重启即丢失。

## 任务目标
用 SQLite、Pydantic、FastAPI 与 React Query 让 Run 的结果在刷新页面和重启 API 后仍然可查询、可追溯。

## 技术栈（本次新增）
- SQLite：保存 Course、Run、Intake、Artifact、Event、Snapshot 的最小业务事实。
- Pydantic：把请求、领域记录和读取响应分开。
- React Query：管理远端事实的加载、错误、刷新与缓存。
- Workspace 目录约定：让课程文件有明确 Course 归属。
- React、FastAPI、LLM Provider 和 Fake Provider 已在前期约定，直接使用。

## 硬约束
- 不要实现 LangGraph、角色分离、完整质量闭环、Worker、lease、checkpoint 或自动发布。
- 七步名称不变，release 仍由人决定，Fake Provider 仅用于测试。
- Snapshot 只是读取投影，不是唯一事实源。
- 不要复制 Demo 的完整表结构或历史兼容逻辑。

## 先分析（不要写代码，先回答以下问题）
1. 为 Course、Run、Intake、Artifact、Event、Snapshot、Workspace 七个对象各写一句职责，明确所有者、稳定 ID、可变性和读取者。
2. 设计最小 SQLite 表与索引，只增加当前需要的字段，不要提前设计未来所有表。
3. 说明当前七步流程如何产生 Event（追加历史）、Artifact（版本化产物）和 Snapshot（读取投影）。
4. 分析 Snapshot 为何不应被误当唯一事实——删掉 Snapshot 后能否从 Event 和 Artifact 重建。
5. 提出迁移策略和重复提交策略——同一请求重放应返回同一受理结果。

## 再实施（分析确认后，按以下顺序逐一完成，每完成一项运行测试再继续下一项）
1. 定义 Course、Run、Intake、Artifact、Event、Snapshot、Workspace 的最小 Schema、ID 与所有权。
2. 建立可重复迁移的 SQLite 表和必要索引。
3. 让 Runner 在各步骤写入 Intake、Artifact、追加 Event，并更新 Snapshot；失败时写失败 Event 与失败 Snapshot。
4. 提供读取 Course、Run、Artifact 与 Snapshot 的 FastAPI 接口。
5. 使用 React Query 改造页面，使硬刷新和 API 重启后仍能恢复 Run。
6. 添加迁移、事务失败、重复提交、重启读取与 Artifact 写入失败测试。

## 更新 AGENTS.md
将本次确定下来的长期约定追加到 AGENTS.md，包括：七个持久化对象的职责与边界、SQLite 迁移策略、Snapshot 的投影定位、Workspace 的目录归属规则、React Query 的缓存策略。

## 完成后留下技术方案
技术方案必须包含：选型理由、模块边界、状态与数据流、失败处理、测试证据、已知限制、下一阶段的冻结契约：对象语义、Artifact 类型与命名、Snapshot 读取方式、Workspace 归属规则。

## 报告格式
每完成一项任务，报告实际运行的命令、退出码和结果。全部完成后按"改动文件、引入的框架/解法、状态/事实变化、实际测试、手工验收、技术方案、剩余风险"七项总结。
```

## AI 交付后的人类 Review

刷新浏览器，确认仍然从 API 得到事实而不是本地缓存。重启 API，确认没有假成功。检查 Event 是否真的是追加历史而不是覆盖。检查 Artifact 是否可以定位到版本。检查 Snapshot 是否只是投影——删掉 Snapshot 应该可以从 Event 和 Artifact 重建。检查 Workspace 是否归属 Course 而不是随意放在某个临时目录。检查 API 是否没有暴露内部 Prompt。检查没有提前加入 Worker 或 Graph 的实现。检查技术方案是否写出了事务语义和重复提交策略。


### 遇到验收问题时

如果你在验收时发现刷新后数据丢失、API 重启后查询结果不一致、Artifact 版本混乱或 Snapshot 和 Event 矛盾——先自行收集 SQLite 迁移版本、Course/Run/Artifact 行、API 响应、Workspace 文件和页面网络请求。然后让 AI 判断问题是迁移、事务、事实所有权、Artifact 版本、Event 追加、Snapshot 投影、API Schema、React Query 缓存还是 Workspace 映射。确认根因后给最小修复，包含回归测试，并说明修复不改变哪些冻结契约。

## AI 做完后重点关注什么

用 SQLite 查询和 API 响应交叉检查，而不是只相信工作台页面。页面可以骗你，但数据库不会。重点追踪一次 Run 的 Artifact、Event 和 Snapshot 如何从同一个源头产生——如果它们之间出现矛盾，说明事实层的设计有问题。确认刷新后页面没有读取旧的本地内存——React Query 的缓存策略是常见的坑。

## 验收关卡

### 自动化关

运行迁移测试、Repository 写入与读取测试、V0 Runner 落账测试、API 重启后的读取测试、前端构建与课程检查。

```bash
apps/api/.venv/bin/pytest -q apps/api/tests
npm --prefix apps/web run build
npm run test:contract
```

### 正常路径

执行一次成功 V0 Run，记录 Course 与 Run 标识。硬刷新工作台，重启 API，重新打开同一 Run。查看 Mission、Blueprint、Lesson 与质量摘要是否仍然存在。查看阶段 Event 是否完整。保存响应、截图和 SQLite 查询结果。

### 失败路径

让 Fake Provider 在 generation 失败，确认失败 Event 与 Snapshot 一致，确认没有成功 Lesson Artifact 被错误创建。再次提交相同请求，确认不会静默覆盖前一次事实。保存失败证据。

### 解释关

Course 和 Run 为什么不能合并成一个对象？Artifact 与 Event 为什么是不同的东西——一个存内容，一个存历史？Snapshot 为什么不应作为唯一事实，而应该可以从 Event 和 Artifact 重建？页面刷新为何是事实层验收而非纯 UI 验收？

## 常见跑偏方式

只把完整 Runner JSON 存进数据库的一列——这样你只是把内存换了个地方，并没有真正分离事实。让 React Query 缓存成为真实状态。用 Event 文案推断当前 Run 状态而不是读 Snapshot。直接编辑生成的 Markdown 而不建 Artifact 版本。让 Workspace 路径由前端随意提交。为了"方便查询"先建未来所有质量和执行表。为了"省事"删掉不可变历史。这些做法都会让阶段 03 到 06 无法清晰地升级——因为每一步都踩在模糊的事实层上。

这些跑偏方式背后有一个共同的根源：把"方便"当成了"正确"。用 JSON Blob 存所有东西是方便，但你失去了独立查询和版本追踪的能力。让 React Query 缓存当事实源是方便，但刷新之后一切归零，你连上一次 Run 的结果都找不回来。先建所有未来表是方便，但那些表里的字段你可能永远用不上，而它们会拖慢每一次迁移和查询。在这个阶段，每多一个"方便"的捷径，都是在为后续阶段埋雷。

## 完成后的系统快照

V0 的七步仍然存在，但现在每次运行都有持久身份，关键输出都可以查询，页面读取的是服务器事实而不是内存变量，失败也有了历史证据。系统仍然没有受控角色，仍然没有 Graph，仍然没有可靠的长任务执行。但你已经有了一个可以信赖的事实层，这是之后所有阶段的基础。

## 下一阶段门槛

数据库重启后仍能读到一致的事实，Artifact、Event 与 Snapshot 的边界可以解释清楚，Workspace 的 Course 归属明确，技术方案已冻结对象语义和读取 Schema。满足后进入[阶段 03](03-skill-aware-roles-and-artifacts.md)，开始把 V0 的万能 Prompt 拆成可审查的角色。
