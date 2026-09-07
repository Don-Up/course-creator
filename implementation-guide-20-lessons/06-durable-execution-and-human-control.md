# 阶段 06：把执行权交给可恢复 Worker

**预计投入：** 8 至 14 小时。

**一句话目标：** 用 Command、Worker、lease、NodeExecution、checkpoint 和持久审批，把长任务从单进程的脆弱依赖变成可接管、可停止、可恢复的执行协议。

**这不是终态：** 能恢复执行了，但交付还没有治理、预算和迁移结论。那是阶段 07 的故事。

## 你将完成什么

到目前为止，你的系统已经能跑通完整的七步流程、有持久化的事实、有分工明确的角色、有受控的 Graph、有可追溯的质量闭环。但有一个问题一直没有解决：执行本身。你的长任务很可能还跑在 API 进程里——浏览器断开可能影响运行，服务重启可能丢失执行权，两个执行者可能同时写结果，停止请求可能和节点提交产生竞争。这不是"再优化一下"能解决的问题，这需要一整套执行权协议。

完成之后，HTTP 接口只受理 Command 而不直接执行任何长任务。Worker 从持久化存储中领取 Command，通过 lease 获得有限期的执行权，定期续约。每个图节点执行时写入 `NodeExecution` 记录，副作用前后有 checkpoint 保存安全恢复位置。Worker 崩溃后，等 lease 过期，另一个 Worker 可以安全接管——从 checkpoint 恢复，检查副作用是否已提交，不会重复写 Artifact。用户可以提交 STOP、RESUME 或 REVISE 命令，这些控制决定是持久化事实，刷新后仍然可见。前端从读模型观察执行状态，不持有执行权。这会是你的系统第一次真正"活"起来——它不再依赖一个浏览器标签页或一个 API 进程才能存活。

## 你现在站在哪里

阶段 05 已有受控图和质量闭环，但执行可能仍在 API 进程或一个临时 Runner 里。本阶段把"谁有权继续执行"变成显式协议——不是多线程优化，是执行权归属。

## 两份 Skill 在本阶段的角色

两份 Skill 不拥有 Worker，不拥有 lease。`teach-generator` 仍然约束节点产物和人工审核，`humanizer-zh` 仍然只产生语言质量输入。执行机制负责可靠地重放已批准的流程，但它不应重新解释 Skill 来修改业务决策——那是在用基础设施僭越领域规则。

## 学习导航

### 本阶段必读

阅读第 05 章的同步异步边界，理解为什么长任务不能绑在 HTTP 请求上。阅读第 16 章的 Command、Worker、lease 与心跳，这是本阶段最核心的参考——它告诉你 Command 如何保存执行意图、Worker 如何领取、lease 如何保护执行权。阅读第 16 章的 checkpoint 与恢复，理解副作用边界和安全恢复位置。阅读第 17 章的人类控制，理解 STOP/RESUME/REVISE 如何变成持久化事实。阅读第 15 章的读模型，理解前端如何安全地观察执行状态。

### 实施时查阅

查阅第 12、13 章的图状态和有界循环，确认 checkpoint 应该保存什么。查阅第 18 章的 Trace，为阶段 07 的可观测性做准备。

### 完成后回看

回看第 18、19 章的治理与失败证据，为阶段 07 的交付做准备。

### Demo 阅读地图

阅读 `apps/api/app/worker.py` 的 Worker 实现，阅读 `apps/api/app/workflow/command_repository.py` 的命令持久化，阅读 `apps/api/app/workflow/repository.py` 的执行记录，阅读 `apps/api/app/workflow/graph.py` 的图执行入口。不要复制部署配置，不要假设多机器队列已存在——你现在只摘录本地执行协议的模式。

## 五类边界

| 范围 | 做什么 | 不做什么 | 理由 |
| --- | --- | --- | --- |
| 前端 | STOP/RESUME/REVISE、执行与审批读模型 | 直接执行节点 | 浏览器无执行权 |
| 后端 | Command API、Worker、lease、checkpoint | 云队列平台 | 先证明本地协议 |
| 数据 | Command、NodeExecution、lease、approval | 全量运维系统 | 持久化执行事实 |
| 运行时 | 单或双 Worker 竞争夹具 | 任意并发扩容 | 先防重复副作用 |
| 测试 | 崩溃、重复领取、停止竞争、恢复 | 跨区域灾备 | 当前风险是接管 |

## 执行权图

```text
HTTP -> Command(PENDING)
          |
Worker A claims lease
          |
NodeExecution STARTED -> checkpoint -> side effect -> COMMITTED
          |
lease expires / Worker crashes
          |
Worker B claims eligible command
          |
resume from durable checkpoint
```

这张图里有几条铁律：只有持有有效 lease 的 Worker 可以提交节点结果，停止 Command 也必须持久化——不能只是一个前端按钮，审批决定不能只存在浏览器里，NodeExecution 不是 Event 的同义词——Event 是"发生了什么"，NodeExecution 是"谁执行了什么、结果如何"，checkpoint 不是业务 Artifact 的替代品——checkpoint 管执行恢复，Artifact 管内容产物。

## 分步任务

### 任务 1：把执行意图做成 Command

START、STOP、RESUME、REVISE 各自有类型，Command 关联 Run，有状态和幂等键。API 成功只表示 accepted——HTTP 200 不再假装任务已完成。完成定义是接口不直接跑长图，证据是 Command API 测试。

### 任务 2：实现 Worker 领取与 lease

领取必须原子化——两个 Worker 同时抢同一个 Command，只有一个能拿到。lease 有持有者和过期时间，Worker 续约必须检查所有权，过期 lease 才可以被接管。完成定义是双 Worker 只能一个获权，证据是竞争测试——同时启动两个 Worker，确认只有一个拿到了 lease。

### 任务 3：记录 NodeExecution

节点开始写 STARTED，节点完成写 COMMITTED，节点失败写 FAILED。每条记录带 Worker 和 lease 信息。完成定义是能解释节点是否真的提交了——不是"节点执行了"，而是"Worker A 在 lease X 内执行了节点 Y，结果为 COMMITTED"。证据是节点历史查询。

### 任务 4：建立 checkpoint

checkpoint 保存安全恢复位置，引用 Graph State 和 Artifact。副作用前后写不同阶段的 checkpoint——写 Artifact 前 checkpoint 说"准备写"，写完后 checkpoint 说"已写完"。恢复时先检查副作用是否已提交，避免重复写。完成定义是不重复写 Artifact，证据是崩溃夹具——模拟副作用后崩溃，确认接管后没有重复的 Artifact。

### 任务 5：持久化人类控制

STOP 优先阻止新节点开始——不是等当前节点跑完，是尽快停止。RESUME 从合法 checkpoint 继续，REVISE 创建明确的人工修订输入。release 审批写入事实。完成定义是刷新后控制决定仍可见，证据是命令与读模型测试。

### 任务 6：实现读模型

页面显示 Command 状态、lease 持有者摘要、当前节点与最后 checkpoint、等待人工的原因。不要把 Worker 内部日志全堆到界面上——用户不需要知道 Worker 的心跳间隔和 lease 剩余秒数，他们只需要知道"正在执行 mission 节点"和"等待人工 release 决定"。读模型的设计原则是：只暴露用户能据此做出决策的信息。如果某个信息不能让用户做出任何决策，它就不应该出现在读模型中。


页面显示 Command 状态、lease 持有者摘要、当前节点与最后 checkpoint、等待人工的原因。不要把 Worker 内部日志全堆到界面上——用户不需要知道 Worker 的心跳间隔，只需要知道"正在执行 mission 节点"和"等待人工 release 决定"。证据是恢复后的页面截图。


## 关于执行权协议的补充说明

执行权协议是本项目中技术复杂度最高的模块，因为它涉及并发、竞争、崩溃恢复和时序——这些都是传统 Web 开发中不常见的关注点。在动手实现之前，有几个关键概念需要先理解清楚。

**为什么 lease 需要过期时间。** 如果 lease 永不过期，Worker 崩溃后，Command 就永远无法被其他 Worker 接管。过期时间不是"Worker 能活多久"的预测，而是"系统愿意等多久才宣布 Worker 死亡"的容忍度。过期时间太短，正常的 Worker 可能因为短暂的高负载而失去 lease；过期时间太长，崩溃后的接管延迟就会很长。在本阶段的教学环境中，30 到 60 秒是一个合理的起点——足够让 Worker 在正常负载下续约，也不会让接管等待太久。

**checkpoint 的位置选择。** checkpoint 不应该在"每个函数调用之后"都写——那样会引入巨大的 I/O 开销。它应该写在副作用边界：在写 Artifact 之前写一个 checkpoint（"准备写"），在写 Artifact 之后写另一个 checkpoint（"已写完"）。恢复时先检查"已写完"的 checkpoint 是否存在——如果存在，说明副作用已经完成，不需要重复；如果只存在"准备写"的 checkpoint，说明副作用可能没有完成，需要重新执行。这个简单策略覆盖了绝大多数崩溃场景。

**STOP 的竞争条件。** 当 STOP 命令到达时，Worker 可能正在执行一个节点。如果你的实现是"等当前节点完成再停止"，那么一个慢节点可能会让 STOP 延迟很久。更好的做法是：在节点执行的关键位置（比如调用 Provider 之前、写 Artifact 之前）检查 Command 状态，如果发现 STOP 已被持久化，节点立即中止并写入 FAILED 的 NodeExecution。这种"协作式停止"比"强制杀死进程"更安全，因为它允许节点在安全的位置退出。

**读模型不是 Worker 日志。** 前端需要的信息是"当前正在执行哪个节点"、"等待人工做什么决定"、"上一次 checkpoint 是什么时候"，而不是 Worker 的心跳间隔、lease 的剩余时间、内部队列的长度。读模型应该过滤掉执行细节，只暴露对用户有意义的执行状态。如果你不确定某个信息是否应该出现在读模型中，问自己：用户看到这个信息后能做什么决定？如果答案是"不能做任何决定"，那它就不应该出现在读模型中。

### 关于测试策略的说明

本阶段的测试是八个阶段中技术难度最高的，因为它们涉及时序和并发。你需要三组核心测试。第一组：双 Worker 竞争测试——同时启动两个 Worker 争抢同一个 Command，确认只有一个拿到 lease。第二组：崩溃恢复测试——在副作用写入后立刻模拟 Worker 崩溃，让 lease 过期，确认新 Worker 接管后不重复写 Artifact。第三组：STOP 竞争测试——在节点执行期间提交 STOP，确认节点在安全位置中止而不是强制杀死。这些测试需要你在测试夹具中控制 lease 的过期时间和 Worker 的崩溃时机，比之前所有阶段的测试都更复杂——但它们是你唯一能证明执行权协议正确的方式。

## 提示词

复制下面这段提示词发给你的 Coding Agent。它会先分析当前系统状态和设计方案，再按顺序逐一实现。

```text
你正在一个包含两份 Skill、AGENTS.md 和完整质量闭环的学习仓库中工作。当前长任务仍依赖 API 进程——崩溃即丢失执行权。

## 任务目标
用 Command、Worker、lease、NodeExecution、checkpoint 和持久审批，把长任务变成可接管、可停止、可恢复的执行协议。

## 技术栈（本次新增）
- Command repository：持久化执行意图，HTTP 只负责受理。
- Worker：从仓储原子领取 Command。
- lease/heartbeat：限定谁在何时可提交结果，过期后可被接管。
- NodeExecution：记录每个节点的尝试和提交。
- checkpoint：在副作用边界保存安全恢复位置。
- STOP/RESUME/REVISE：把人类控制变成持久化事实。
- read model：让前端只读执行状态，不持有执行权。
- Graph、角色、质量闭环、Artifact 等已在前期约定，直接使用。

## 硬约束
- 不要引入云队列、分布式部署或新的质量语义。
- 业务 Skill 规则不变，不自动发布。
- POST 只返回 accepted，不要让 API 请求等待整次生成。
- 浏览器不能持有执行权——关掉浏览器，Worker 继续跑。

## 先分析（不要写代码，先回答以下问题）
1. 输出 Command 状态机、lease 协议、NodeExecution/Checkpoint 关系、停止竞争规则和故障夹具。
2. 分析 lease 为什么需要过期时间——太短正常 Worker 可能失权，太长崩溃后接管延迟过大。
3. 分析 STOP 的竞争条件：STOP 到达时节点正在提交怎么办？应协作式停止而非强制杀进程。
4. 按五类边界拆成 3 至 6 个小任务，每项写证据、测试与不做事项。

## 再实施（分析确认后，按以下顺序逐一完成，每完成一项运行测试再继续下一项）
1. 为 START、STOP、RESUME、REVISE 定义关联 Run 的持久化 Command、状态和幂等键。
2. 实现 Worker 从仓储原子领取 Command，并用有持有者和过期时间的 lease 获得执行权。
3. 为每个 Graph 节点写入 STARTED、COMMITTED 或 FAILED 的 NodeExecution。
4. 在副作用前后写 checkpoint；恢复前检查相应 Artifact 是否已经提交。
5. 让 STOP 阻止新节点开始，让 RESUME 从合法 checkpoint 继续，让 REVISE 形成持久人工输入。
6. 提供只读执行工作台，显示 Command、当前节点、最后 checkpoint 和等待人工原因。
7. 添加双 Worker 竞争、lease 过期接管、副作用后崩溃、STOP 竞争和 RESUME/REVISE 测试。

## 更新 AGENTS.md
将本次确定下来的长期约定追加到 AGENTS.md，包括：Command 类型和状态机、lease 的过期时间策略、checkpoint 的写入位置、STOP/RESUME/REVISE 的语义、读模型的设计原则。

## 完成后留下技术方案
技术方案必须包含：选型理由、模块边界、状态与数据流、失败处理、测试证据、已知限制、下一阶段的冻结契约：执行标识、事件、checkpoint 位置、控制命令类型。

## 报告格式
每完成一项任务，报告实际运行的命令、退出码和结果。全部完成后按"改动文件、引入的框架/解法、状态/事实变化、实际测试、手工验收、技术方案、剩余风险"七项总结。
```

## AI 交付后的人类 Review
AI 交付代码之后，你亲自做三个实验。第一，启动 Worker，让它执行一个节点，然后手动杀掉 Worker 进程，等 lease 过期，启动另一个 Worker，确认它接管了任务。第二，同时启动两个 Worker，确认只有一个拿到了 lease。第三，在 Worker 执行期间提交 STOP，确认节点在安全位置中止。这三个实验比你跑任何测试都更能让你理解执行权协议的实际行为。


检查 POST 是否只创建了 Command 而不是直接执行——如果 POST 返回时任务已经跑完了，说明执行权还在 API 进程里。检查 Worker 是否只执行持久化的命令，检查 lease 是否有期限，检查过期接管是否安全——新 Worker 接管前是否确认了旧 lease 已过期。检查副作用前后是否有 checkpoint，检查 STOP 是否不是 UI 假动作——按钮变了但 Worker 还在跑。检查 RESUME 是否不重做已提交的 Artifact，检查审批是否可刷新读取。检查技术方案是否明确了竞争窗口。


### 遇到验收问题时

如果你在验收时发现双 Worker 都拿到了 lease、崩溃后接管时重复写 Artifact、STOP 到达后节点仍在执行、RESUME 从错误位置恢复——先自行收集 Command、Run、Worker、lease、NodeExecution、checkpoint、Artifact/Event 和测试输出。然后让 AI 判断问题是 Command 状态、领取原子性、lease、心跳、NodeExecution、checkpoint、停止竞争、读模型还是页面投影。确认根因后给最小修复和回归测试，并说明修复保留的冻结契约。

## AI 做完后重点关注什么

查看 Command、lease、NodeExecution 和 checkpoint 的关联，而不是只看 Worker 日志。重点复演三个场景：Worker 崩溃后 lease 过期接管、两个 Worker 同时抢同一个 Command、STOP 命令和节点提交之间的竞争。确认浏览器从读模型观察执行状态，不持有执行权——如果你关掉浏览器，Worker 应该继续跑。

## 验收关卡

### 自动化关

运行 Command 状态机测试、双 Worker 领取竞争测试、lease 过期接管测试、副作用后崩溃恢复测试、STOP 与节点提交竞争测试、RESUME/REVISE 读模型测试。

```bash
apps/api/.venv/bin/pytest -q apps/api/tests
npm --prefix apps/web run build
npm run test:contract
```

### 正常路径

提交 START Command，观察 Worker 领取并执行，观察节点执行与 checkpoint 的写入，观察质量后等待人工，提交 release 决定，查看读模型。保存 Command、NodeExecution 和截图。

### 失败路径

在 generation 副作用后模拟 Worker 崩溃，让 lease 过期，启动第二个 Worker 接管，确认已提交的 Artifact 不重复。再提交 STOP，确认新节点不再开始。保存所有关联标识。

### 解释关

为什么 Command 不等于 Worker——一个存意图，一个执行？为什么 lease 需要过期时间而不是"永久有效"？为什么 checkpoint 不等于 Artifact——一个管恢复，一个管内容？停止为什么也存在竞争条件——如果 STOP 命令到达时节点正在提交怎么办？

## 常见跑偏方式

让 API 线程执行整个 Graph，让 Worker 从前端 payload 取状态，没有 lease 直接启动多个 Worker，只记录日志不记录 NodeExecution，在副作用后才首次写 checkpoint，STOP 只改变按钮文字但 Worker 还在跑，恢复时盲目重跑所有节点。这些做法会重新制造不可解释的执行——你会以为自己有 Worker，实际上只是把 V0 的 Runner 换了个名字。

这些跑偏方式背后有一个共同的根源：在执行权的战场上使用"乐观策略"。乐观策略假设一切都会顺利——Worker 不会崩溃、lease 不会过期、STOP 不会有竞争。但执行权协议之所以存在，恰恰是因为这些假设不成立。如果你让 API 线程直接执行长任务，你是在假设服务永远不会重启。如果你没有 lease 就启动多个 Worker，你是在假设它们永远不会同时操作同一个数据。如果你在副作用后才写 checkpoint，你是在假设崩溃永远不会发生在副作用中途。执行权协议不是锦上添花，它是你唯一能保证系统在异常情况下行为正确的机制。

## 完成后的系统快照

执行意图现在可以持久化，执行权现在有所有者和期限，节点有尝试和提交的事实，崩溃可以从安全位置接管，人类控制可以刷新读取。系统仍然需要最终交付证据与治理判断——那是阶段 07 的故事。

每个阶段都是在前一个阶段的基础上建立起来的。你现在做出来的东西，会成为下一阶段的起点——好的起点让你事半功倍，模糊的起点让你举步维艰。花几分钟确认你真的理解了本阶段的每一个设计决策，然后带着信心进入下一阶段。

## 下一阶段门槛

正常、崩溃接管和人工控制路径都有证据，双 Worker 竞争可重复测试，技术方案冻结执行与控制契约。满足后进入[阶段 07](07-delivery-governance-and-migration.md)，用三条路径的证据完成最终交付。
