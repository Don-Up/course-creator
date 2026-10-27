name: code-change-report

description: Generate a code change summary report focused on business flow and architecture, not API/decorator details. 
---

报告风格要通俗易懂(优先使用高频常用的词汇)，保留必要的专业术语，而不是书面化的技术文档风格。

主要目标是帮助读者快速理解业务变化并更新心智模型。因此，报告应以宏观视角为主，重点关注中上层的核心业务、流程、架构等，只涉及少量重要的技术细节即可，避免让读者消化大量的底层技术细节。

数据流是报告中最重要的部分，规则也比较复杂，生成报告后，务必根据SKILL中的数据流规则自测一下。

---

### 第一部分：Q&A 概览

这些问题应让读者快速理解业务变化和心智模型更新，而不是技术细节。

偏向核心业务和中上层的技术点。

问答数量的最大值5个，需要精选出最能帮助读者快速理解业务变化的问答。

采用中英混合的格式，每个Q&A的中文答案的字数应该在100字以内，例如:

| Question             | Answer                          |
| -------------------- | ------------------------------- |
| Content?【中文翻译】 | Content.【中文翻译(100字以内)】 |

1. 文本风格要适合TTS朗读，感觉像是老师在耐心讲解，优先使用高频常用的词汇，而不是书面词汇或非地道词汇。
2. 中文统一放到【】内，且【中文翻译】后面不要加标点符号。
3. 禁止使用Q1和A1之类的前缀

---

### 第二部分：数据流

为当前任务总结除1-2条核心数据流(标题要通俗易懂，挑重要的，与项目心智模型密切相关的)；每个子段 = 1 个 `dataflow` 块。每个dataflow块由数据流图 + JSON 讲解 + 代码区域构成。

数据图 + JSON 讲解 + 代码区域必须放在同一个```dataflow```块中，用"---"行隔开，代码区域无需放入一个```某种代码语言```块中。 "---"行在```dataflow```块中只能出现两次，不要在一个代码区域内的不同的代码片段之间插入"---"。

另外，在每篇数据流```dataflow```之前放置一个简化版的mermaid流程图或时序图，用来在阅读数据流之前进行"热身"；流程图下面再补一张 3 列表格，把图里画不出来的信息补齐。

返回格式:

```mermaid
<简化版流程图:只画主干和分支,不要画细节;节点用中文短句>
```

| 步骤简称 | 状态快照 | 说明 |
| --- | --- | --- |
| <该节点涉及的几步简称,用→连接> | <变量名[简介]: 当前值> | <这一步对用户意味着什么> |

其中:

- **步骤简称** —— 取数据流图里每一步的中文简称(如 `连接抖断`、`计失败`);一个节点跨了多步就用 `→` 连接,例如 `连接抖断 → 计失败 → setState → 关源`。
- **状态快照** —— 该节点走完之后相关变量的**当前值**,格式和 JSON 讲解里【】里面完全一致:`变量名[简介]: 当前值`,多个变量用 `<br>` 换行。**简介用中文**,写清这个变量是什么。
- **说明** —— 该节点对用户意味着什么,和 JSON 讲解里【】左边的补充解释保持一致。

```dataflow
数据流图

---

JSON讲解

---

代码区域
```

#### 步骤编号

数据流里的每一步都用 `数字-数字` 编号,例如 `1-01`、`2-01`。

- **第一个数字由数据流图的缩进决定**:缩进回到最左边的那一行,就是新一段的开始,第一个数字 +1;这一段里往右缩进的所有行,第一个数字不变。
- **第二个数字**是这一步在这一段里的顺序,从 1 开始往下数,补到两位(`1-01` 到 `1-12`),这样同一张图里所有编号等宽,箭头才对得齐。
- 同一个编号在三处必须完全一致:**数据流图**的行首、**JSON 讲解的键**、**代码区域的 `//` 注释**。

举例(左边是缩进,右边是编号):

```text
1-01 (用户改标题) 步骤描述...
1-02   → (persist 触发) 步骤描述...
1-03        ↳ [挑要存的] 步骤描述...
2-01 (用户刷新) 步骤描述...          ← 缩进回到最左边,进入第 2 段
2-02   → (store 重建) .步骤描述..
2-03        ↳ [节点回来了] .步骤描述..
```

数据流中的步骤描述: 一律使用技术名词(变量名/方法名/类名等)搭配自然语言的形式，这样可以与通俗化的JSON讲解相互呼应。同时技术名词要注音解释，例如: [[EventSource]]服务器实时推送通道}} 触发 [[onerror()]]连接失败回调}},可能是网络瞬断或后端关停。可视化工具会把 `[[` 转成 `<ruby>`、`]]` 转成 `<rt>`、`}}` 转成 `</rt></ruby>`。另外，方法名后面一律加()以区别于普通变量。

#### JSON讲解注意事项

每一步的讲解分成两段，中间用【】隔开:

- **【】左边 —— 当前步骤的补充解释**。数据流图那一行只说了"做了什么"，这里补上"这意味着什么、用户会看到什么"。**不要复述代码**(代码图里已经有了)，只讲后果和用户能感知到的效果。
- **【】里面 —— 当前步骤的状态快照**。这一步走完之后，各相关变量的**当前值**，格式 `变量名[这个变量是什么]: 当前值`，多个变量用 `\n` 分隔。**只写当前值，不写箭头**(`值1 → 值2` 这种变化流不要写)——下一步的快照本身就说明了变化。

**叙述部分一律用英文**;但【】里的**变量简介用中文**,和图里 ruby 注音的中文解释保持一致。按照下面这个公式来:

{
  "步骤序号":"supplementary explanation of this step【techVar1[这个变量是什么]: current value\ntechVar2[这个变量是什么]: current value】"
}

讲解使用英文，适合TTS朗读，优先使用通俗易懂的表达，而不是艰涩的代码和技术名词。

**判定边界**(避免乱标):

- 只有"修饰成分跟在中心词后面"才算后置修饰。**动词的介词宾语不算**,例如 "land on the drop zone" 里的 "on the drop zone" 是 land 的宾语,不是名词的后置修饰。
- 【】里的变量说明不用加标记,那里写的是变量名和解释,不是散文。

##### 不好的讲解: 纯技术讲解

canAccept looks up REGISTRY['tabs'].slots[0] = {key:'tab-1', accepts:['btn','text']} and sees btn sitting in the whitelist → true.

##### 推荐的讲解: 通俗化讲解或技术+通俗化讲解

1. 通俗化讲解: canAccept checks the whitelist of tab-1, and lets 'btn' through because it is in there.
2. 技术+通俗化讲解(技术表达后面要跟一句通俗解释，讲解用英文时写成 "which means" / "that means")，例如: 
   a. handleDrop reads dataTransfer.getData("application/x-lowcode-id") and gets 'card', which means the component id that was dragged in is 'btn'.
     b. closest("[data-slot-zone]") hits the tab-1 zone div, which means the drop landed on the droppable area of tab-1.

##### 变量性质或含义要简短易懂:

1. 不好的做法: raw[entryId 字符串,DataTransfer.getData 读出来的]
2. 好的做法(读者一目了然): raw[拖进来的那个组件 id]

#### 代码片段注意事项

1. 非常重要: 任何涉及代码的步骤，一定要贴上对应的代码片段，如果没有对应的代码片段，则附上ASCII图。
2. 精准标注步骤的注释(// 1-1 // 1-2 // 1-3等)，让读者迅速定位到对应的代码，该注释一定要在对应代码的上方，不能是右侧。
3. 禁止将多个步骤序号放在同一行代码注释中，例如// 1-01(选中网格) / 1-02(用户改) ，这会导致数据流可视化工具无法定位给到后面的序号。
4. 在每个步骤的前面添加通俗精简的总结性的步骤中文关键词，放到[]中。
5. 在代码区域的上方添加一条步骤链注释: 例如, // STEP FLOW: 1-1[浏览器订阅] → 1-2[路由到] → ...
6. 添加代码所在文件的注释，需要说明文件的性质，例如: // ===== 📂 controller/ExportSseService.java(SSE长连接推送服务) =====
7. 在STEP FLOW注释下方增加一条比喻化的注释(根据STEP FLOW)，让读者更好地理解整条STEP FLOW
8. 每个步骤涉及的标识用 **ruby 注音写法**就地标在步骤描述里,格式为 `[[标识]]极简通俗解释}}`,例如 `[[EventSource]]服务器实时推送通道}}`、`[[consecutiveFailuresRef]]记失败次数的计数器}}`。
   解释要让读者不看代码也知道这个名字是干什么的;同一步骤里出现多个标识就各自标一个,不要漏。
   可视化工具会把 `[[` 转成 `<ruby>`、`]]` 转成 `<rt>`、`}}` 转成 `</rt></ruby>`,渲染成注音形式 —— 比把一堆解释堆在行尾好读得多,所以**不要**再写 `标识[解释]` 这种方括号形式。
   步骤行末尾只保留 `<{文件名}>` 标出这一步的代码位置,例如 `<{useExportEvents.ts}>`;该步骤没有可标的标识时也只写文件路径。
9. **代码区域里,该步"步骤描述"中谈到的技术名词用 `<*` `*>` 包裹**,例如 `const <*hasWidth*> = widthStyle !== undefined;`。
   可视化工具会对包裹部分做特殊处理(高亮 / 与步骤描述联动),开发者读代码时能一眼对上是哪一步在讲它。
   - **只包这一步"步骤描述"里点名提到的标识**(变量名 / 函数名 / 方法名 / 属性链),提到几个包几个;
   - 这一步没提到的标识(局部变量、循环变量、纯语法)不要包;
   - 属性链整体包一个:`<*ev.clientX*>`;方法调用只包方法名,括号和参数留在外面:`e.<*preventDefault*>() <*setNodeWidth*>(id, w)`。
   - **JSX 标签的尖括号留在包裹外面**,所以看起来是两个 `<`,不是笔误:组件 `<<*ResizeHandle*> nodeId={id} />`、属性 `<*draggable*>={false}`。
     去掉标记后分别还原成 `<ResizeHandle nodeId={id} />` 和 `draggable={false}`,代码含义不变。


例如:

```mermaid
flowchart TD
    ERR(["长连接断开 onerror"]) --> CNT["失败次数 +1"]
    CNT --> BR{"失败不到 3 次?"}
    BR -->|是| WAIT["按退避表等待<br/>1s / 2s / 5s / 10s"]
    WAIT --> RECON["重开一条长连接"]
    RECON -->|通了| LIVE["回到实时模式<br/>失败计数清零"]
    RECON -->|没通| ERR
    BR -->|否| POLL["切到轮询模式<br/>徽标变黄"]
    POLL --> PROBE["30 秒后再探一次"]
    PROBE -->|通了| LIVE
    PROBE -->|没通| POLL

    OFF(["浏览器断网 offline"]) --> CLOSE["关连接 + 清定时器<br/>徽标变红"]
    BACK(["网络恢复 online"]) --> RESET["清空状态 + 立刻重连"]
    HIDE(["切走标签页 hidden"]) --> QUIET["关连接 + 清定时器<br/>徽标不变"]
    SHOW(["切回标签页 visible"]) --> FRESH["立刻拉一次最新数据"]
    FRESH --> RESET
```

| 步骤简称 | 状态快照 | 说明 |
| --- | --- | --- |
| 连接抖断 → 计失败 → setState → 关源 | `EventSource.readyState[长连接当前的状态]: connecting`<br>`consecutiveFailuresRef.current[连着失败了几次]: 1`<br>`sourceRef.current[指向长连接的指针]: gone` | The long link drops. The helper counts the failure, shows the number on screen, and shuts the broken connection down. |
| 算下次退避 → failCount<3 → 退避序列 | `failCount[失败次数]: 1`<br>`backoff[这一次要等多久]: 1 second` | It checks how many times in a row this has gone wrong, then waits 1 second before the next try. |
| 到点重建 → open 成功 | `reconnectTimerRef.current[等一会儿再动的闹钟]: set`<br>`consecutiveFailuresRef.current[连着失败了几次]: 0`<br>`mode[当前连接方式]: live` | The alarm rings, a brand new long connection opens, and the page goes back to live mode. |
| failCount>=3 → 列表自动轮询 → 30s probe | `mode[当前连接方式]: polling`<br>`refetchInterval return value[列表多久自己刷一次]: every 3 seconds`<br>`probeTimer.current[30 秒后再试一次的闹钟]: set` | After 3 failures in a row it stops rushing, asks the list for fresh data every 3 seconds, and still tries the long link every 30 seconds. |
| 切 Badge | `CONNECTION_BADGE['polling'][轮询时显示的小徽标]: yellow` | The badge turns yellow, so the user knows the live link is gone and polling took over. |
| 浏览器断网 → 强制关 → 切 Badge | `navigator.onLine[电脑有没有联网]: no`<br>`sourceRef.current[指向长连接的指针]: gone`<br>`mode[当前连接方式]: offline` | If the network drops completely, the helper closes everything and the badge turns red. |
| 网络恢复 → 强制重连 | `navigator.onLine[电脑有没有联网]: yes`<br>`mode[当前连接方式]: connecting` | When the network comes back, the helper clears all its state and reconnects from scratch. |
| 用户切走标签 → 关 SSE | `document.hidden[这一页有没有被藏起来]: hidden`<br>`sourceRef.current[指向长连接的指针]: gone`<br>`mode[当前连接方式]: live, no flicker` | When the user leaves the tab, the helper closes the link and the timers, but leaves the badge alone. |
| 用户切回标签 → invalidate → 重建 | `document.hidden[这一页有没有被藏起来]: not hidden`<br>`React Query cache ['export-jobs'][浏览器记住的那份列表]: marked stale`<br>`sourceRef.current[指向长连接的指针]: a new connection` | When the user comes back, the helper pulls fresh data first, then opens a new link if one is needed. |

```dataflow
1-01 (连接抖断) [[EventSource]]服务器实时推送通道}} 触发 [[onerror()]]连接失败回调}},可能是网络瞬断或后端关停 <{useExportEvents.ts}>
1-02      → [计失败] [[consecutiveFailuresRef]]记失败次数的计数器}}.[[current]]计数器里存的次数}} += 1(同步镜像) <{useExportEvents.ts}>
1-03           ↳ [setState] [[setConsecutiveFailures()]]把失败次数写进界面状态}}(n => n + 1) + [[setMode()]]切换连接方式}}('connecting') <{useExportEvents.ts}>
1-04                ↳ [关源] [[sourceRef]]指向长连接的指针}}.current.[[close()]]关掉这条连接}} + sourceRef.current = null <{useExportEvents.ts}>
1-05                ↳ [算下次退避] [[failCount]]这次算出来的失败次数}} = consecutiveFailuresRef.current <{useExportEvents.ts}>
1-06                     ↳ failCount < 3:[[scheduleReconnect()]]安排重连}} 按 [[BACKOFF_MS]]每次等多久的清单}}[failCount-1] 启动 [[setTimeout()]]闹钟,到点再动}} <{useExportEvents.ts}>
1-07                          ↳ [退避序列] [[BACKOFF_MS]]每次等多久的清单}}: 1 → 1000ms / 2 → 2000ms / 3+ → 5000ms(封顶 10000) <{useExportEvents.ts}>
1-08                          ↳ [到点重建] [[connect()]]打开长连接的函数}} 重新 new [[EventSource]]服务器实时推送通道}} <{useExportEvents.ts}>
1-09                               ↳ [[open()]]连接成功时触发的回调}} 成功 → [[consecutiveFailuresRef]]记失败次数的计数器}}.current = 0 + [[setMode()]]切换连接方式}}('sse'),回到 sse <{useExportEvents.ts}>
1-10                     ↳ failCount >= 3:[[setMode()]]切换连接方式}}('polling') + 30s 启动 [[probeTimer]]30 秒后再试一次的闹钟}} <{useExportEvents.ts}>
1-11                          ↳ [列表自动轮询] [[useExportJobs()]]拉任务列表的 hook}} 看到 [[sseConnected]]长连接是否正常}}=false,列表里 PENDING/RUNNING 时每 3s 拉一次 <{useExportJobs.ts}>
1-12                          ↳ [30s probe] 到点调 [[connect()]]打开长连接的函数}} 探一次,[[open()]]连接成功时触发的回调}} 成功 → [[setMode()]]切换连接方式}}('sse'),失败 → 继续 polling <{useExportEvents.ts}>
2-01 (切 Badge) [[CONNECTION_BADGE]]各种状态下徽标文案的清单}}['polling'] = { status: 'warning', text: '实时连接不可用，已切换轮询' } <{useExportEvents.ts}>
3-01 (浏览器断网) [[window]]浏览器窗口}} 派发 [['offline']]断网了的事件名}} 事件 <{useExportEvents.ts}>
3-02      → [强制关] [[forceOfflineRef]]断网时强制关连接的开关}}.current() → [[closeSource()]]关掉长连接}} + [[clearTimers()]]清掉所有闹钟}} + setMode('offline') <{useExportEvents.ts}>
3-03           ↳ (切 Badge) [[CONNECTION_BADGE]]各种状态下徽标文案的清单}}['offline'] = { status: 'error', text: '网络离线' } <{useExportEvents.ts}>
4-01 (网络恢复) [[window]]浏览器窗口}} 派发 [['online']]恢复联网的事件名}} 事件 <{useExportEvents.ts}>
4-02      → [强制重连] [[forceOnlineRef]]恢复联网时强制重连的开关}}.current() → 清 fail / 清 [[lastSeenVersions]]已经看过的消息版本}} / setMode('connecting') + [[connect()]]打开长连接的函数}} <{useExportEvents.ts}>
5-01 (用户切走标签) [[document]]当前网页}} 派发 [['visibilitychange']]页面可见状态变了的事件名}} 且 document.[[hidden]]这一页有没有被藏起来}} === true <{useExportEvents.ts}>
5-02      → [关 SSE] 关闭 [[sourceRef]]指向长连接的指针}},清 timers,[[mode]]当前的连接方式}} 保持 sse 不闪 <{useExportEvents.ts}>
6-01 (用户切回标签) [[document]]当前网页}} 派发 [['visibilitychange']]页面可见状态变了的事件名}} 且 document.[[hidden]]这一页有没有被藏起来}} === false <{useExportEvents.ts}>
6-02      → [invalidate] 立刻 [[queryClient]]管着缓存的总管}}.[[invalidateQueries()]]把缓存标记为过期}}(['export-jobs']) 拉最新 <{useExportEvents.ts}>
6-03           ↳ [重建] [[sourceRef]]指向长连接的指针}} 为 null 时调 [[forceOnlineRef]]恢复联网时强制重连的开关}}.current() 重新建 [[EventSource]]服务器实时推送通道}} <{useExportEvents.ts}>
---
{
  "1-01": "The long link just dropped. It might be the network flickering for a moment, or the backend going down.【EventSource.readyState[长连接当前的状态]: connecting\nbrowser[出了什么事]: error event fired】",
  "1-02": "The helper counts the failure on the inside, so it knows how many times in a row this has gone wrong.【consecutiveFailuresRef.current[连着失败了几次]: 1】",
  "1-03": "It also bumps the number the user can see, and puts the badge back to 'connecting' so they know it is retrying.【consecutiveFailures[页面上显示的失败次数]: 1\nmode[当前连接方式]: connecting】",
  "1-04": "It shuts down the connection that is already broken, so nothing keeps using it.【EventSource instance[那条已经断掉的连接]: closed\nsourceRef.current[指向长连接的指针]: gone】",
  "1-05": "It peeks at the internal counter to decide the next move.【failCount[失败次数]: 1 (read out of that counter)】",
  "1-06": "If it has not hit 3 yet, it tries again, but waits first, and waits longer every time.【failCount[失败次数]: 1 (still under 3)\nbranch[这次走哪条路]: the retry branch】",
  "1-07": "The first wait is 1 second, the second 2 seconds, the third 5 seconds, and after that it caps at 10 seconds.【BACKOFF_MS[每次等多久的清单]: 1s / 2s / 5s / 10s (picked by the failure count)\nbackoff[这一次要等多久]: 1 second (the first failure)】",
  "1-08": "Once the wait is over, the helper opens a brand new long connection.【reconnectTimerRef.current[等一会儿再动的闹钟]: set (it will ring)\ncountdown[闹钟上还剩多少秒]: 1 second】",
  "1-09": "The new connection comes up, the counter is cleared, and it goes back to live mode.【consecutiveFailuresRef.current[连着失败了几次]: 0\nmode[当前连接方式]: live\nEventSource.readyState[长连接当前的状态]: connected】",
  "1-10": "If it has already failed 3 times in a row, it stops rushing to reconnect, switches to polling, and tries again in 30 seconds.【mode[当前连接方式]: polling\nprobeTimer.current[30 秒后再试一次的闹钟]: set】",
  "1-11": "In polling mode the list asks the server for data every 3 seconds, but only while at least one job is still running.【refetchInterval return value[列表多久自己刷一次]: every 3 seconds (only while a job is alive)】",
  "1-12": "Every 30 seconds the helper tries the long connection again; if it works it goes back to live mode, if not it keeps polling.【probeTimer[30 秒后再试一次的闹钟]: ringing\nmode[当前连接方式]: live if the probe worked, still polling if it did not】",
  "2-01": "The badge turns yellow and says the live connection is unavailable and it has switched to polling, so the user knows what happened.【CONNECTION_BADGE['polling'][轮询时显示的小徽标]: yellow, 'live connection unavailable, switched to polling'】",
  "3-01": "If the user's network drops completely, the browser sends an offline signal.【navigator.onLine[电脑有没有联网]: no\nwindow[浏览器自己]: fired the offline event】",
  "3-02": "The helper closes the long connection, clears every timer, and switches to offline mode.【sourceRef.current[指向长连接的指针]: gone\nreconnectTimerRef.current[等一会儿再动的闹钟]: gone\nmode[当前连接方式]: offline】",
  "3-03": "The badge turns red and says the network is offline, so the user spots it at a glance.【CONNECTION_BADGE['offline'][离线时显示的小徽标]: red, 'network offline'】",
  "4-01": "The network comes back and the browser sends an online signal.【navigator.onLine[电脑有没有联网]: yes\nwindow[浏览器自己]: fired the online event】",
  "4-02": "The helper clears every bit of state and reconnects from scratch.【consecutiveFailuresRef.current[连着失败了几次]: 0\nlastSeenVersions[已经看过哪些消息]: empty (all over again)\nmode[当前连接方式]: connecting, ready to reconnect】",
  "5-01": "The user switches to another tab and the browser sends a hidden signal.【document.hidden[这一页有没有被藏起来]: hidden\ndocument[当前网页]: fired the visibility change event】",
  "5-02": "The helper closes the long connection and clears the timers; the badge stays put, so nothing flickers and startles.【sourceRef.current[指向长连接的指针]: gone\nevery timer (reconnect / probe)[各种会等的闹钟]: gone\nmode[当前连接方式]: live, no flicker】",
  "6-01": "The user comes back and the browser sends a visible signal.【document.hidden[这一页有没有被藏起来]: not hidden\ndocument[当前网页]: fired the visibility change event】",
  "6-02": "The helper immediately asks the server for the freshest data, so the user sees something new.【React Query cache ['export-jobs'][浏览器记住的那份列表]: marked stale (it will refetch next time)】",
  "6-03": "If the long connection is gone, it opens a new one.【sourceRef.current[指向长连接的指针]: a new connection\nmode[当前连接方式]: live】",
  "Summary": "Every connection error goes through the same little state machine. Fewer than 3 failures and the helper keeps trying with a steadily longer wait; at 3 the page quietly switches to polling every 3 seconds. The browser's offline event and the tab-switch-away event both feed this one state machine through the same set of switches, so going offline or switching away leaves no stray timers behind and never breaks the page."
}
---
// STEP FLOW: 1-01(连接抖断) → 1-02[计失败] → 1-03[setState] → 1-04[关源] → 1-05[算下次退避] → 1-06[failCount<3] → 1-07[退避序列] → 1-08[到点重建] → 1-09[open 成功] → 1-10[failCount>=3] → 1-11[列表自动轮询] → 1-12[30s probe] → 2-01(切 Badge) → 3-01(浏览器断网) → 3-02[强制关] → 3-03(切 Badge) → 4-01(网络恢复) → 4-02[强制重连] → 5-01(用户切走标签) → 5-02[关 SSE] → 6-01(用户切回标签) → 6-02[invalidate] → 6-03[重建]

// 整条流程可以想象成你跟朋友打电话:电话一断你就重拨,但每次等得越来越久(1s/2s/5s/10s,失败 < 3 次),
// 连拨 3 次还打不通就别死磕,改用微信每 3 秒问一下近况(切 polling),但每 30 秒还是会再试一次电话(probe)。
// 手机直接没信号(window offline)就放下电话彻底休息,信号一回来(online)立刻重新拨;走开去做别的事(切走标签)
// 就把电话挂掉省电,回来时(切回标签)先看一眼消息再重拨。

// ===== 📂 hooks/useExportEvents.ts(SSE 长连接状态机 hook) =====
// 1-01[连接抖断] 入口:error 监听器
<*source*>.addEventListener('error', () => {
  if (cancelledRef.current) return;
  // 1-02[计失败] 同步镜像
  <*consecutiveFailuresRef*>.current += 1;
  // 1-03[setState] React state 镜像
  <*setConsecutiveFailures*>(n => n + 1);
  // 1-03[setState] 切回「正在连接」状态
  <*setMode*>('connecting');
  // 1-04[关源] 释放坏连接
  <*closeSource*>();
  // 1-05[算下次退避] 三分支决策
  <*scheduleReconnect*>();
});

function <*scheduleReconnect*> {
  // 1-05[算下次退避] 读内部计数器
  const <*failCount*> = consecutiveFailuresRef.current;
  // 1-10[failCount>=3] 切 polling 分支
  if (<*failCount*> >= 3) {
    // 1-10[切 polling] 切状态
    <*setMode*>('polling');
    // 1-12[30s probe] 启动 probe 定时器
    <*probeTimer*>.current = <*setTimeout*>(connect, POLLING_PROBE_MS);
    return;
  }
  // 1-06[failCount<3] 计算 backoff
  const backoff = <*BACKOFF_MS*>[Math.min(failCount - 1, BACKOFF_MS.length - 1)];
  // 1-07[退避序列] 1s/2s/5s/10s 数组
  // 1-08[到点重建] 启动 setTimeout
  reconnectTimerRef.current = <*setTimeout*>(connect, backoff);
}

// 3-02[强制关] 浏览器断网监听
<*window*>.addEventListener('offline', () => <*forceOfflineRef*>.current());
// 4-02[强制重连] 网络恢复监听
window.addEventListener('online', () => {
  if (mode === 'offline') <*forceOnlineRef*>.current();
});

// 5-02[关 SSE] 标签页切走时关连接
// 6-02[invalidate] 标签页切回时拉最新
// 6-03[重建] 标签页切回时重建 SSE
function onVisibilityChange() {
  if (document.hidden) {
    // 5-02[关 SSE] 关闭 sourceRef、清 timers
    <*closeSource*>(); clearTimers();
  } else {
    if (sourceRef.current === null && !cancelledRef.current) {
      // 6-02[invalidate] 拉最新
      void <*queryClient*>.invalidateQueries({ queryKey: ['export-jobs'] });
      // 6-03[重建] 重新建 EventSource
      <*forceOnlineRef*>.current();
    }
  }
}

// ===== 📂 hooks/useExportJobs.ts(导出任务列表查询与轮询 hook) =====
// 1-11[列表自动轮询] 入口:sseConnected=false 时启动轮询
refetchInterval: (query) => {
  if (<*sseConnected*>) return false;
  // 1-11[列表自动轮询] 扫 PENDING/RUNNING 任务
  const hasActive = query.state.data?.items.some(
    (i) => i.status === 'PENDING' || i.status === 'RUNNING');
  // 1-11[列表自动轮询] 返 3000ms 触发 React Query 自动重拉
  return hasActive ? 3_000 : false;
};

// 1-09[open 成功] 连上了:失败次数清零,连接方式回到实时
┌──────────────┐       ┌─────────────────────┐
│ open() 回调  │   →   │ 失败次数: 1 → 0     │
│ 连接真的通了 │       │ mode: 连接中 → 实时 │
└──────────────┘       └─────────────────────┘

// 2-01[切 Badge] 状态一变,小徽标跟着换文案和颜色
┌───────────┐       ┌──────────────────┐       ┌────────────────────┐
│ mode 变了 │   →   │ CONNECTION_BADGE │   →   │ 黄底「已切换轮询」 │
│ 'polling' │       │ 查表拿徽标       │       │ 黄色 warning       │
└───────────┘       └──────────────────┘       └────────────────────┘

// 3-01[浏览器断网] 电脑断网,浏览器自己派发 offline 事件
┌───────────────────┐       ┌────────────────┐       ┌────────────────────┐
│ 电脑断网          │   →   │ window 派发    │   →   │ 页面上的监听器接住 │
│ 网线 / Wi-Fi 断了 │       │ 'offline' 事件 │       │ → 走「强制关」     │
└───────────────────┘       └────────────────┘       └────────────────────┘

// 3-03[切 Badge] 断网了,小徽标换成红色
┌───────────┐       ┌──────────────────┐       ┌──────────────────┐
│ mode 变了 │   →   │ CONNECTION_BADGE │   →   │ 红底「网络离线」 │
│ 'offline' │       │ 查表拿徽标       │       │ 红色 error       │
└───────────┘       └──────────────────┘       └──────────────────┘

// 4-01[网络恢复] 网络回来了,浏览器自己派发 online 事件
┌───────────────────┐       ┌───────────────┐       ┌────────────────────┐
│ 网络恢复          │   →   │ window 派发   │   →   │ 页面上的监听器接住 │
│ 网线 / Wi-Fi 接回 │       │ 'online' 事件 │       │ → 走「强制重连」   │
└───────────────────┘       └───────────────┘       └────────────────────┘

// 5-01[用户切走标签] 页面被藏起来,浏览器派发 visibilitychange
┌──────────────┐       ┌─────────────────┐       ┌───────────────────────┐
│ 用户切到别的 │   →   │ document.hidden │   →   │ 派发                  │
│ 标签页       │       │ false → true    │       │ visibilitychange 事件 │
└──────────────┘       └─────────────────┘       └───────────────────────┘

// 6-01[用户切回标签] 页面又露出来了,浏览器再派发一次 visibilitychange
┌──────────────┐       ┌─────────────────┐       ┌───────────────────────┐
│ 用户切回这个 │   →   │ document.hidden │   →   │ 派发                  │
│ 标签页       │       │ true → false    │       │ visibilitychange 事件 │
└──────────────┘       └─────────────────┘       └───────────────────────┘
```

### 第三部分：其它（可选）

你完全自由发挥。