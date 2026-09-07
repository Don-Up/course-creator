# 阶段 03：让角色按 Skill 与 Artifact 协作

**预计投入：** 6 至 10 小时。

**一句话目标：** 用 Agent Definition、Provider 接口、Pydantic Schema 与受控 Tool，把 V0 那个什么都做的万能 Prompt 拆成五个各司其职、可独立审查的角色。

**这不是终态：** 角色已经分工，但执行顺序、上下文裁剪和恢复机制还没有可靠的保障。你的系统现在知道"谁做什么"，但还不知道"按什么顺序做"和"失败了怎么继续"。

## 你将完成什么

V0 跑通的时候，你大概率有一个巨大的 Prompt，同时定义课程、列出目录、写正文、检查质量并决定下一步该做什么。它能跑，但问题也很明显：输出是自由文本，解析靠运气，错误难以定位到具体职责，权限也无法限制。当蓝图出错时，Writer 会带着错误继续写；当质量问题出现时，你不知道该让谁修复。

这个阶段要解决的就是这个问题。完成之后，Mission 角色只生成任务定义，Blueprint 角色只生成课程结构，Writer 角色只生成指定章节的候选正文，Reviewer 角色只产生审查结论，Repair 角色只处理明确的 Finding。每个角色读取自己需要的 Skill 规则片段——不是整份 Skill 无差别复制——每个角色有明确的输入 Schema 和输出 Schema，有明确的允许 Tool 列表，角色之间通过 Artifact 交接而不是自由聊天。Provider 可以被 Fake Provider 替换，错误输出能被拒绝而非静默解析。这会是你第一次真正感受到"架构"的力量——不是因为你用了什么框架，而是因为每个组件都有清楚的边界。

## 你现在站在哪里

阶段 02 已经让结果持久化了，但 V0 的生成逻辑很可能仍然是一个大 Prompt。它同时做太多事情，输出常常是自由文本，错误难以定位，权限也难以限制。本阶段用角色契约与 Artifact 交接来替换这个万能 Prompt——不是把它拆成五个更小的万能 Prompt，而是给每个角色定义清楚的目标、输入、输出、权限和失败行为。

## 两份 Skill 在本阶段的角色

`teach-generator` 被按角色切片加载。Mission 读取任务定义、受众、范围和停止条件规则；Blueprint 读取来源、学习路径、章节类型和蓝图规则；Writer 读取正文写法、前置解释与可观察证据规则；Reviewer 读取量规与确定性质量规则；Repair 只读取当前 Finding 所需的最小规则。不要把整份 Skill 无差别地塞进每一个 Prompt——如果你这样做，本质上还是 V0 的万能 Prompt，只是换了五个名字。

`humanizer-zh` 只授予中文学生可见文本的编辑角色或语言 Reviewer。它不授予 Mission、Blueprint 或 release 的决策权。它的判断仍然需要被验证——它说"这段文字太机械"，但最终是否接受这个判断、如何修改，是 Reviewer 和 Repair 的工作。

## 学习导航

### 本阶段必读

阅读第 02 章的 Skill、Tool、MCP 与 Agent 边界，再次确认 Skill 和 Agent 的区别。阅读第 07 章的 Prompt 与结构化输出，理解如何让模型输出可解析的结果。阅读第 08 章的 Artifact 合约，理解什么是可交接的产物。阅读第 10 章的 Provider 边界，理解为什么要隔离模型调用。阅读第 11 章的 Agent Definition，这是本阶段最核心的参考——它告诉你角色如何被定义、如何被约束。

### 实施时查阅

查阅第 09 章的 Schema 与解析失败，了解如何处理非法输出。查阅第 10 章的 Tool 权限，了解如何限制角色的能力。查阅第 14 章的 Context Pack，虽然本阶段不实现完整的上下文裁剪，但你需要知道这个方向。

### 完成后回看

回看第 12 章的 Workflow，为阶段 04 的 Graph 做准备。回看第 13 章的 Finding 与 Repair，为阶段 05 的质量闭环做准备。

### Demo 阅读地图

阅读 `apps/api/app/agents/runtime.py` 的接口设计，阅读 `apps/api/app/agents/fake_runtime.py` 的替身实现，阅读 `apps/api/app/workflow/definitions.py` 的角色定义，阅读 `apps/api/app/workflow/repository.py` 的 Artifact 写入。不要复制所有生产 Prompt，不要接 MCP 平台——你现在只摘录角色定义的模式。

## 五类边界

| 范围 | 本阶段要做 | 本阶段不做 | 理由 |
| --- | --- | --- | --- |
| 前端 | 展示角色产出的 Artifact 与拒绝错误 | 聊天式多 Agent 面板 | 用户应看结果，不是内部争论 |
| 后端 | Agent Definition、Provider、Schema、Tool 适配 | 图路由与 Worker | 先固定角色契约 |
| 数据 | Artifact 类型、版本、输入引用 | 全量质量关系 | 先保证交接可追溯 |
| 运行时 | Fake/真实 Provider 可替换、受控 Tool | 自由 ReAct 循环 | 不交出流程控制权 |
| 测试 | Schema、权限、角色输入输出 | 图恢复 | 当前风险是契约漂移 |

## 角色交接图

```text
Intake Artifact
  -> Mission Agent + teach-generator slice
  -> Mission Artifact
  -> Blueprint Agent + teach-generator slice
  -> Blueprint Artifact
  -> Writer Agent + chapter brief
  -> Lesson Candidate Artifact
  -> Reviewer / Humanizer Gate
  -> Finding or verified summary
```

这条交接链有几个关键约束：角色只读取它需要的 Artifact 而不是整个数据库，角色输出必须符合 Schema 而不是自由文本，角色不直接批准 release，Tool 必须先被调用方授权才能使用。这些约束看起来是"限制"，但它们保护的是系统的可审查性——如果任何一个角色可以随意读、随意写、随意决定流程，你之前画的七步责任图就形同虚设。

## 分步任务

本阶段的任务顺序是刻意安排的：先定义角色和 Schema，再定义 Provider 和 Tool，最后才替换 V0 的大 Prompt。这个顺序保证你在替换之前，已经对每个角色的边界、输入、输出和权限有了清晰的认知。不要在还没定义 Schema 的情况下就开始"拆分 Prompt"——那样你会得到一个形式上拆开了但实质上仍然混乱的系统。

### 任务 1：定义 Agent Definition

为 Mission、Blueprint、Writer、Reviewer、Repair 各写一个 Agent Definition。每个角色写清楚目标、输入 Artifact 类型、输出 Artifact 类型、加载的 Skill 片段、允许的 Tool 列表和失败类型。完成定义是这些定义可以序列化，并且可以通过测试验证——比如"Mission 角色不能以 Writer 的身份被调用"。证据是可序列化的定义与对应的测试。

### 任务 2：定义 Provider 接口

接口接收结构化请求，返回结构化候选或可分类的错误。Fake Provider 实现相同的接口，真实 Provider 不应改变领域逻辑——它只是换了模型，不是换了业务规则。完成定义是 Provider 可替换——同一个角色用 Fake Provider 和真实 Provider 应该产生相同结构的输出。证据是同一角色测试使用两种 Provider 都通过。

### 任务 3：定义输出 Schema

Mission 输出目标、受众、范围和停止条件。Blueprint 输出章节及前置关系。Writer 输出标题、正文、练习和元数据。Reviewer 输出 Finding 候选而不是一句"通过"。解析失败必须显式失败——不能把一个格式错误的 JSON 当成"模型没生成完"悄悄忽略。证据是非法输出测试，确认每种非法输出都能被正确拒绝。

### 任务 4：限制 Tool

先定义读取 Artifact 的 Tool，再定义写候选 Artifact 的 Tool。禁止 Writer 直接发布，禁止 Humanizer 改写来源事实，禁止角色直接更新 Run 状态。证据是越权 Tool 被拒绝的测试——比如 Writer 试图调用 publish tool，应该被拒绝并记录。

### 任务 5：替换 V0 大 Prompt

保留 V0 的可见流程——七步仍然在页面上依次显示——但每一步的内部实现从"一个大 Prompt"变成了"一个角色 + Schema 验证 + Tool 调用"。这个任务的关键不是"把代码拆开"，而是"保留 V0 的用户体验，同时替换 V0 的内部实现"。用户应该感觉不到变化——他们看到的仍然是七步、仍然是 Fake Provider 的输出、仍然是人工 release。但你现在可以独立地检查、测试和修改每一个角色了。


保留 V0 的可见流程，但让每一步调用对应的角色，让输出先被 Schema 验证再写 Artifact，失败时保留拒绝原因。不要在本阶段更换为 LangGraph——V0 的执行顺序暂时保持不变，只是每一步内部的实现从"一个大 Prompt"变成了"一个角色 + Schema + Tool"。证据是成功 Run 和格式失败 Run 的完整记录。


## 关于角色设计的补充说明

在写 Agent Definition 之前，有几个关键的设计决策值得你停下来想一想，因为它们是本阶段最容易出错的地方。

**Skill 切片而不是复制。** 每个角色只加载 Skill 中与自己相关的部分，而不是整份 Skill。Mission 角色需要受众定义、学习目标、范围、停止条件的规则，但它不需要正文写法、量规或 Humanizer 的规则。如果你把整份 teach-generator 塞给每个角色，你实际上还是在用万能 Prompt，只是换了五个名字。一个实用的做法是：先在 Skill 文本中标注每个段落属于哪个角色的职责，然后让角色只加载标注为自己职责的段落。

**Schema 严格但不过度。** Schema 的目标是保证输出可以被后续流程可靠地消费，而不是穷举所有可能的字段。Mission 的 Schema 需要受众、目标、范围、停止条件——因为它们直接影响后续 Blueprint 和 Writer 的质量。但如果你的 Schema 要求 Mission 必须包含"建议的课程时长"而 teach-generator 并没有这个要求，你就是在替 Skill 做决定。Schema 应该反映 Skill 的约束，而不是发明新的约束。

**Tool 权限的粒度。** 本阶段只定义最基础的 Tool：读取 Artifact 和写入候选 Artifact。不要提前定义"搜索来源"、"调用外部 API"、"发送通知"等 Tool——它们会在后续阶段按需引入。关键是权限检查的位置：在副作用发生之前，而不是之后。如果 Writer 试图调用 publish Tool，权限检查应该在 publish 函数执行之前就拒绝，而不是等到文件已经写入再报错。

**Provider 接口的职责边界。** Provider 接口只做一件事：接收结构化请求，返回结构化候选或错误。它不应该包含业务逻辑——不应该在 Provider 内部决定"如果 Mission 写得太短就重试"，不应该在 Provider 内部缓存结果，不应该在 Provider 内部记录业务事件。这些是角色或 Workflow 的职责。Provider 是纯函数，同样的输入应该产生相同结构的输出。这让你可以在 Fake Provider 和真实 Provider 之间无缝切换，也让测试变得可预测。

### 关于测试策略的说明

本阶段的测试有三个层次。第一层是 Schema 验证测试——用合法的输出确认它能通过，用非法的输出确认它能被拒绝，而且拒绝信息足够明确。第二层是 Tool 权限测试——确认 Writer 不能调用 publish、Humanizer 不能调用改写事实源的 Tool、任何角色不能直接更新 Run 状态。第三层是 Provider 替换测试——同一组输入，用 Fake Provider 和真实 Provider 分别运行，确认输出结构一致。这三个层次分别验证了"输出是否正确"、"权限是否受限"、"实现是否可替换"——它们合在一起，构成了你对角色契约的信心。

## 提示词

复制下面这段提示词发给你的 Coding Agent。它会先分析当前系统状态和设计方案，再按顺序逐一实现。

```text
你正在一个包含两份 Skill、AGENTS.md 和完整持久化实现的学习仓库中工作。当前七步流程通过一个轻量 Runner 串行执行，但每一步内部仍用一个 Prompt 混合所有职责——任务定义、蓝图、写作、审查都混在一起。你的任务是把 Runner 中每一步的"大 Prompt"替换为"角色 + Schema + Tool"，但 Runner 本身的调用顺序保持不变。

## 任务目标
用 Agent Definition、Provider 接口、Pydantic Schema 与受控 Tool，把万能 Prompt 拆成五个各司其职、可独立审查的角色。

## 技术栈（本次新增）
- Agent Definition：声明角色目标、输入输出、Skill 片段和 Tool 权限。
- Pydantic Schema：拒绝自由文本解析漂移，确保输出可被后续流程消费。
- Provider interface：隔离 LLM Provider 与 Fake Provider，两者使用同一接口。
- Artifact handoff：角色之间通过可追溯的 Artifact 交接，不自由聊天。
- 受控 Tool：读取和写入 Artifact 的 Tool 必须在副作用前检查权限。
- SQLite、React、FastAPI、LLM Provider 已在前期约定，直接使用。

## 硬约束
- 不要实现 LangGraph 路由、批次并发、完整 Finding/Repair 循环、Worker、lease、checkpoint 或自动发布。
- 七步产品形状不变，Fake Provider 仅用于测试，Humanizer 只做语言质量，release 由人决定。
- 不要为每个角色复制整份 Skill——应按角色切片加载。

## 先分析（不要写代码，先回答以下问题）
1. 为 Mission、Blueprint、Writer、Reviewer、Repair 五个角色各自写出：目标、输入 Artifact、输出 Artifact、Skill 片段、允许 Tool、拒绝条件。
2. 分析每个角色不应承担的责任——Writer 不能发布、Humanizer 不能核验事实、任何角色不能直接更新 Run 状态。
3. 按前端、后端、数据、运行时、测试五栏列出 3 至 6 个小任务，每项给验证与失败证据。

## 再实施（分析确认后，按以下顺序逐一完成，每完成一项运行测试再继续下一项）
1. 定义 Mission、Blueprint、Writer、Reviewer、Repair 五个 Agent Definition。
2. 定义 Provider interface，让 LLM Provider 与 Fake Provider 使用同一结构化请求和响应。
3. 用 Pydantic 为 Mission、Blueprint、Lesson 与 Review 输出建立严格 Schema，解析失败必须可见。
4. 定义读取 Artifact、写候选 Artifact 的最小 Tool contract，在副作用前拒绝越权调用。
5. 让当前流程各步骤调用对应角色并通过 Artifact 交接，保留可见的七步流程。
6. 添加 Schema 非法输出、Provider 替换、Tool 越权和 Artifact 引用测试。

## 更新 AGENTS.md
将本次确定下来的长期约定追加到 AGENTS.md，包括：五个角色的 Definition 与 Skill 切片规则、Provider 接口规范、Artifact 交接约定、Tool 权限检查位置、Schema 解析失败的处理方式。

## 完成后留下技术方案
技术方案必须包含：选型理由、模块边界、状态与数据流、失败处理、测试证据、已知限制、下一阶段的冻结契约：角色名、Artifact 类型、Schema 结构、Tool 权限清单。

## 报告格式
每完成一项任务，报告实际运行的命令、退出码和结果。全部完成后按"改动文件、引入的框架/解法、状态/事实变化、实际测试、手工验收、技术方案、剩余风险"七项总结。
```

## AI 交付后的人类 Review
AI 交付代码之后，你不要只看每个角色是否"能跑"。更重要的是检查每个角色的边界是否真的独立——如果你发现 Mission 角色的输出里包含了"建议的章节结构"，那说明它越界了，它在做 Blueprint 的事。如果你发现 Reviewer 的输出里包含了"修改后的正文"，那说明它在做 Repair 的事。角色的边界是在 Definition 和 Schema 中定义的，不是在运行时靠"自觉"维护的。


检查每个角色是否只有一个清楚的目标——如果 Mission 角色也在写正文，说明边界有问题。检查每个角色不是整份 Skill 的复制品——它们应该只加载自己需要的规则片段。检查 Writer 不能发布，Reviewer 不能重写全部课程，Humanizer 不承担事实判断。检查 Provider 没有藏业务状态，检查 Schema 失败是否可见而不是被吞掉，检查 Artifact 是否有来源与类型，检查 Tool 越权是否可以被拒绝。检查技术方案是否冻结了角色和 Artifact 的契约。


### 遇到验收问题时

如果你在验收时发现角色输出不符合 Schema、Tool 越权未被拒绝、Provider 替换后行为不一致或角色之间通过非 Artifact 方式通信——先自行检查 Agent Definition、Artifact 关联、Provider 请求响应、Schema 错误和 Tool 拒绝记录。然后让 AI 判断问题是 Skill 切片、Definition、Schema、Provider、Tool、Artifact 引用还是页面投影。确认根因后给最小修复和回归测试，并说明修复保留哪些冻结契约。

## AI 做完后重点关注什么

沿着一次角色调用完整追踪：它读到了什么输入 Artifact，加载了哪段 Skill 规则，通过了什么 Schema 验证，调用了什么 Tool，产出了什么输出 Artifact。不要接受"角色分开了"但每个角色仍然共享一个万能 Prompt 或无限权限的实现。确认每次 Schema 解析失败都有事实证据，而不是一个笼统的"解析错误"。

## 验收关卡

### 自动化关

运行 Agent Definition 测试、Schema 成功和失败测试、Fake Provider 替换测试、越权 Tool 拒绝测试、Artifact 交接测试。

```bash
apps/api/.venv/bin/pytest -q apps/api/tests
npm --prefix apps/web run build
npm run test:contract
```

### 正常路径

开始一次小课程 Run，查看 Mission Artifact 是否包含受众和目标，查看 Blueprint Artifact 是否包含章节结构，查看 Writer 的 Lesson Candidate 是否符合 Schema，查看角色和 Artifact 的关联是否可追溯。确认 Humanizer 只出现在质量记录中而不是其他角色里。保留 Run、Artifact 与响应证据。

### 失败路径

让 Fake Provider 返回非法 Blueprint，确认 Schema 拒绝它，确认不会产生伪造的 Blueprint Artifact。让 Writer 请求未授权的发布 Tool，确认在副作用前被拒绝。保留错误和测试证据。

### 解释关

为什么 Skill 不是 Agent Definition，而是 Agent Definition 引用了 Skill？为什么 Provider interface 不应包含流程决策——也就是不应该在 Provider 内部决定下一步走哪个角色？为什么角色之间使用 Artifact 交接而不是互相聊天？为什么 Tool 权限必须在副作用前检查，而不是事后审计？

## 常见跑偏方式

每个角色都加载整份规则而不是切片，把角色拆得极细却没有 Artifact 边界，让模型自由选择下一个角色，把 Pydantic 变成宽松的 `dict` 来"兼容各种输出"，让 Writer 直接写发布目录，只记录最终文本而不记录输入引用，提前接入复杂的 MCP 平台。这些做法都会让阶段 04 的控制图无法明确——因为角色之间的边界是模糊的，Graph 就无法确定应该怎么路由。

这些跑偏方式背后有一个共同的根源：把"角色拆分"当成了"把 Prompt 拆成五份"。角色拆分的目的是让每个角色有独立的输入、输出、权限和失败行为，不是把万能 Prompt 的文本复制到五个不同的文件里。如果你发现自己的五个 Agent Definition 里有大量重复的 Skill 文本和相同的 Tool 权限，那说明你还没有真正理解"角色"的含义——角色不是因为它们做不同的事情而不同，而是因为它们有不同的责任边界。

## 完成后的系统快照

系统已经知道谁做什么——Mission 不会去写正文，Writer 不会去定义课程目标。系统已经知道每个输出如何验证——Schema 拒绝非法输出，Tool 拒绝越权调用。系统已经知道谁能调用什么能力——每个角色有一份明确的 Tool 清单。系统仍按 V0 的函数顺序运行，仍可能携带过多上下文，仍没有受控批次或恢复点。但你已经有了可审查的角色边界，这是之后所有控制机制的基础——一个没有边界的系统，无论加多少控制都是徒劳。

系统已经知道谁做什么，已经知道每个输出如何验证，已经知道谁能调用什么能力。系统仍按 V0 的函数顺序运行，仍可能携带过多上下文，仍没有受控批次或恢复点。但你已经有了可审查的角色边界，这是之后所有控制机制的基础。

每个阶段都是在前一个阶段的基础上建立起来的。你现在做出来的东西，会成为下一阶段的起点——好的起点让你事半功倍，模糊的起点让你举步维艰。花几分钟确认你真的理解了本阶段的每一个设计决策，然后带着信心进入下一阶段。

## 下一阶段门槛

每个角色有定义、Schema、Skill 片段与 Tool 权限，所有角色通过 Artifact 交接，非法输出和越权行为可观察，技术方案冻结角色、Artifact、Schema 和权限。满足后进入[阶段 04](04-graph-context-and-batch-control.md)，用 LangGraph 给这些角色一个明确的执行顺序和恢复边界。
