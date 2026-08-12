# 第 3 章 插件架构拆解与云端 API 快速落地

> 预计学习时间：150–240 分钟
> 一句话总结：拆解 Smart Connections 和 Copilot 的运行机制，理解它们在本地索引、云端调用和流式输出上的核心差异，并亲手为 Obsidian 接入第一个远程大模型，让知识库可以对话搜索。

## 你的第一个问题：插件对笔记做了什么？

在第 2 章，你已经学会了如何用原子化笔记和 YAML Frontmatter 为 RAG 准备高质量语料，并用 AST 做了结构感知分块。现在要面对一个现实：那些 `.md` 文件安静地躺在你的硬盘里，但 AI 模型需要的不是原始的 Markdown 文本，而是一组能计算“语义距离”的嵌入向量（Embedding）。谁来做这个转换？当你用自然语言提问知识库时，又是谁把你的问题变成向量并找出相关的笔记段落？这就是本章要回答的问题：AI 插件究竟对笔记做了什么，以及它如何连接到远端的“大脑”。

## 两种模式，两个流派

把 Obsidian 生态里的主流 AI 插件放到一起看，你会发现它们并不只是“界面不同”。它们在对笔记的处理方式和依赖的外部服务上，存在根本性的架构分歧。这一节先建立这个认知地图，然后我们分别深入两种模式的代表插件。

**模式甲：本地优先索引，云端可选推理** —— 以 Smart Connections 为代表。它在本地处理你的所有 Markdown 文件，计算每个段落的嵌入向量并存入本地存储。当你提问时，它从本地索引中检索相关段落，然后可以选择发送给云端模型生成最终答案，或者（在第 4 章会实现）全部在本地完成。

**模式乙：上下文窗口组装，云端直接推理** —— 以 Copilot 和 Smart Composer 为代表。它不预先建立索引，而是在你每次提问时，把你的活跃笔记内容、选中的文本或者整个文件夹的 Markdown 文件打包成一个巨大的提示词（Prompt），直接扔给云端大模型，让模型“现场阅读”来回答问题。

| 对比维度 | Smart Connections 模式（索引模式） | Copilot 模式（上下文模式） |
| --- | --- | --- |
| 笔记预处理 | 全部笔记预先向量化，存入本地索引 | 无预处理，提问时才读取文件 |
| 提问时耗时 | 检索 + 模型生成（秒级响应） | 读取文件 + 拼装提示词 + 模型生成（文件和文件夹较大时显著变慢） |
| 知识覆盖范围 | 可搜索全部笔记（全库检索） | 只覆盖你选中的文件或文件夹 |
| 本地依赖 | 需本地或远程 Embedding 模型 | 无（直接使用云端 LLM） |
| 离线可用性 | 高（索引在本地，配合本地模型可离线） | 无（离开云端 API 无法工作） |
| 代表插件 | Smart Connections | Copilot、Smart Composer |

这两种模式的本质区别，就是“先检索再回答”和“全量上下文现场理解”的区别。打个比方：索引模式像你给一本书做了详细索引，查某个概念时翻到对应页码就行；上下文模式则像你每次考试都把整本课本摊开在桌上，题目问哪一页你看哪一页。课本薄还好，但你的知识库只会越来越厚。

## 深入 Smart Connections：本地向量工厂的内部运作

Smart Connections 是 Obsidian 社区中一个很适合拆解的 AI 插件，因为它清晰展示了“把 Markdown 变成知识”的全流程。我们从它启动后对你的文件做了什么开始。

### 第一步：文件监听与变更感知

你安装并启用 Smart Connections 后，它做的第一件事不是连网，而是注册 Obsidian 的 **文件系统事件**。Obsidian 插件 API 暴露了 `vault.on('create')`、`vault.on('modify')` 和 `vault.on('delete')` 事件。插件会在 `onload()` 方法里注册这些事件的回调函数。这意味着每当你在 Obsidian 里新建、修改或删除一个 `.md` 文件，Smart Connections 都会立刻收到通知。

```typescript
// 概念示意（非 Smart Connections 源码，用于说明事件注册逻辑）
this.registerEvent(
    this.app.vault.on('modify', async (file) => {
        if (file instanceof TFile && file.extension === 'md') {
            await this.indexer.updateFile(file);
        }
    })
);
```

这个 `updateFile` 调用并不会立即执行向量化。如果它每次保存都重新生成向量，你连续敲一个字就触发一次完整索引，CPU 会直接飙满。所以它有一个**去抖（Debounce）机制**：文件修改后，插件会等待一个短暂静默期（比如 30 秒内没有新修改），才真正开始重新处理。

> **可观察证据**：打开 Obsidian 的开发者控制台（Ctrl/Cmd + Shift + I），切换到 Console，然后修改一个笔记并快速保存两次。你会看到 Smart Connections 只在最后一次保存后才有日志输出，而非每次保存都触发。

### 第二步：Markdown 分块与内容提取

当去抖时间到，插件开始处理这个文件。此时发生的事和你在第 2 章手动做的工作高度对应：

1. **读取文件原始内容**。
2. **解析 Frontmatter**：提取 metadata，如标签、别名等。这些元数据在后续检索时可以作为过滤器。
3. **分块**：Smart Connections 不按固定字符数切分，而是使用 Markdown 的结构边界——通常以标题或空行作为块的边界。这和你在第 2 章实现的 AST 标题递归切分思想一致，但实现更简单：按 `\n\n`（空行）分段，再将相邻短段落合并为一个语义完整的块。
4. **生成唯一哈希**：每个文本块会生成一个哈希值作为唯一标识，用于后续比对（判断块是否真的变了，而不是整个重新向量化）。

**关键认知**：如果你在第 2 章已经为笔记做了正确的原子化设计和 YAML 元数据规划，那么 Smart Connections 在这里产出的块就会非常干净。换句话说，**写作的质量决定了索引的质量**。

**边界：当笔记不是规范的 Markdown 时**。如果你的一篇笔记只有连续的大段纯文本，没有标题、没有空行分隔，甚至包含从网页直接粘贴来的混乱换行，Smart Connections 会退回使用长度阈值（如 800 个 token）强制切分。这样的块很可能会在段落中间被截断，导致一个完整想法被拆成两块，或者两个无关想法被强行合并——检索时间要么漏掉关键信息，要么返回一大段噪音。这是**前端输入质量决定后端检索上限**的典型例子。你可以自己验证：新建一篇纯文本笔记，写 2000 字无空行的内容，然后查看索引文件里该笔记产生了几个块，每个块的开头和结尾在哪。你会发现切点毫无语义。

### 第三步：调用 Embedding 模型生成向量

文本块准备好之后，Smart Connections 把每个块的内容发送给 Embedding 模型。这个模型可能是一个远程 API（默认使用的是 OpenAI 的 `text-embedding-3-small` 或 `text-embedding-ada-002`），也可能是一个本地模型（你可以在设置里换成 Ollama 提供的本地 Embedding 接口）。

模型接收到文本块后，返回一个固定长度的数值数组（向量），比如 1536 维。这一步是 Smart Connections 的唯一网络出口（如果使用远程模型）。**你的原始笔记文本不会被发送到远端，只有分割后的文本块被发送以换取向量**。

### 第四步：写入本地存储

生成的向量被写入 `.obsidian/plugins/smart-connections/` 目录下的本地文件。视插件版本不同，存储格式可能是：

- **JSON 文件**：结构清晰，可直接用文本编辑器查看
- **SQLite 数据库**：更高效的查询，但需要 SQLite 浏览器查看
- **Dedicated Vector Store**：类似迷你版的向量数据库

无论哪种格式，每条记录都包含三个核心字段：**文本块的哈希 ID、原始文本内容（或路径引用）、对应的嵌入向量**。

> **动手观察**：打开你的 Obsidian vault，导航到 `[你的 vault]/.obsidian/plugins/smart-connections/`，你会看到文件结构。找到 `data.json` 或 `embeddings.json`，检查其中的向量存储部分。如果插件已经完成索引，JSON 文件通常会明显变大（从初始的几 KB 增长到 MB 级别），因为里面存了很多浮点数组。本章末尾的实战环节会教你如何定位和解读这些文件。

### 第五步：检索阶段

当你通过 Smart Connections 的聊天窗口或搜索框提问时：

1. 你的问题被同样的 Embedding 模型转换成向量。
2. 插件将问题向量与本地存储中所有文本块的向量逐一计算**余弦相似度**。
3. 返回相似度最高的 Top-K 个文本块（默认 10-20 个）。
4. 将这些文本块和一个系统提示词组装成最终 Prompt，发送给 LLM（如果配置了的话）。

整个过程对用户透明，但从工程角度看，这正是一个标准 Naïve RAG 管道在桌面应用中的实现。

**短小可观察示例：在你眼前算一次余弦相似度**。在 Obsidian 控制台中粘贴以下 JavaScript 代码（向量用随机数模拟，但逻辑真实）：

```javascript
function cosineSim(a, b) {
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    magA += a[i] * a[i];
    magB += b[i] * b[i];
  }
  return dot / (Math.sqrt(magA) * Math.sqrt(magB));
}

// 模拟两个文本块的向量（真实的是 1536 维，这里缩到 4 维便于观察）
const queryVec = [0.8, 0.1, 0.05, 0.05];      // 查询“Python 变量作用域”
const blockA = [0.7, 0.15, 0.1, 0.05];        // 块 A 讲 Python 作用域
const blockB = [0.0, 0.0, 0.9, 0.1];          // 块 B 讲浏览器缓存
console.log("相似度 (query vs blockA):", cosineSim(queryVec, blockA)); // 接近 1
console.log("相似度 (query vs blockB):", cosineSim(queryVec, blockB)); // 接近 0
```

你会看到 `query` 与 `blockA` 的相似度远高于与 `blockB` 的相似度。这就是 Smart Connections 筛选相关块的数学原理——每一次搜索都是全库向量的余弦相似度计算。

**Smart Connections 的局限**：因为向量计算在本地进行（哪怕是 JSON 解析和纯 JS 计算），当知识库超过几万块时，纯 JavaScript 的向量遍历会成为瓶颈。这也是为什么它适合个人使用，而不适合作为企业级 RAG 引擎的原因——企业系统会用专门的向量数据库（如 Pinecone、Qdrant）来管理亿级向量，并用近似最近邻算法加速检索。

## 深入 Copilot / Smart Composer：上下文窗口的搬运工

与 Smart Connections 的“先建索引”思路完全不同，Copilot 和 Smart Composer（本章统称为“Copilot 系插件”）的架构哲学是：**不做预处理，让 LLM 直接阅读你的笔记**。

### 工作流总览

1. **触发方式**：你在某个文件里用快捷键呼出对话窗，或在侧边栏打开 AI 面板，此时插件会收集上下文。
2. **上下文收集**：插件根据你的设置，抓取活跃文件内容、当前选中的文本、指定文件夹下的所有 Markdown 文件，甚至是你在对话中 @ 引用的特定文件。
3. **提示词组装**：插件将系统指令、你的笔记内容、你的问题按顺序拼接成一个巨大的文本块。
4. **API 调用**：整块文本被发送给 OpenAI、DeepSeek 或 Claude 等兼容接口。
5. **流式输出**：模型开始逐个 token 返回生成结果，插件实时插入到 Obsidian 画布中。

### 它的核心挑战：上下文窗口管理

Copilot 系插件的工程挑战不是向量检索，而是**上下文窗口（Context Window）的管理**。大语言模型一次能“吞下”的文本量是有限的（如 128K tokens）。如果你的活跃文件加上 @引用的文件总长度超过这个窗口，插件必须做取舍。

常见策略：**按文件顺序截断**——先加入的文件先保留，超出窗口长度后直接丢弃后面的内容。这意味着如果你 @ 引用了 5 个大文件，排在最后的文件内容可能根本不会被发送给模型。更聪明的插件会做 **“滑动窗口 + 小结”**：如果上下文太长，先把前面的内容让模型做一次摘要，用摘要替代原文，为后面的内容腾出空间。

**反例：上下文截断如何误导模型**。不妨做一个小实验——不写代码，只靠观察：创建三个笔记 A、B、C，每个笔记写约 500 字的不同内容。在笔记 A 的开头写下“最重要的配置是 `maxConn=10`”，在笔记 C 的末尾写下“注意：上述 `maxConn=10` 是示例，生产环境必须设为 50”。提问时，故意把 A、B、C 三个文件同时 @ 给 Smart Composer，然后问“生产环境 maxConn 应该是多少？”。如果插件按文件顺序截断，C 会被丢弃，模型只会看到 A 里的 10，回答成“10”——这正是生产事故的种子。这个实验说明**上下文窗口管理是 Copilot 系插件正确性的生命线**，一旦截断位置不当，模型只能基于残缺信息作答，而且不会告诉你它“没看到”后面的纠正。

**与 Smart Connections 的关键差异**：Copilot 系插件**不知道你的整个知识库里有什么**。它只使用你显式或隐式给它的文件。如果你想问“我的知识库里有哪些关于 Go 语言的笔记”，除非你手动把所有 Go 标签的文件 @ 进上下文，否则它无法回答。而 Smart Connections 的向量索引天然支持全库检索。

### 流式输出：SSE 的幕后工作

当模型开始返回结果时，你不会看到一个加载中的旋转图标直到全部完成。你会发现文字像打字机一样一个字一个字地出现。这是通过 **SSE（服务器发送事件，Server-Sent Events）** 实现的。

在现代 LLM 的 API 调用中，如果你设置了 `stream: true`，服务器不会在全部生成完成后一次性返回，而是持续推送单 token 的数据块：

```
// SSE 数据流示例（每次推送一个 token）
data: {"choices":[{"delta":{"content":"你"}}]}
data: {"choices":[{"delta":{"content":"好"}}]}
data: {"choices":[{"delta":{"content":"，"}}]}
...
data: [DONE]
```

Obsidian 插件在 JavaScript 中通过 `fetch` API 接收流，并逐片更新 DOM（文档对象模型，在这里就是笔记内容编辑区），实现打字机效果。这个看似“炫酷”的效果背后，没有任何魔法，只有从网络字节流到 UI 组件的逐帧刷新。

## 实战：为 Obsidian 接入 DeepSeek 云端大模型

了解了两大流派的架构，现在做三件事：
1. 安装 Smart Connections，观察它的索引生成过程。
2. 为 Obsidian 配置 DeepSeek API，跑通对话。
3. 检查插件数据目录，验证索引数据的存在。

> **安全提示**：接下来的操作会让插件将部分笔记内容发送给 DeepSeek API 服务器以换取向量和/或对话回复。如果你想保证完全不联网，本章只做理解性阅读，实际操作留到第 4 章全本地部署时完成。如果你有 DeepSeek API Key 且对联网不抗拒（所有商业 RAG 服务都经过云端），可以现在就开始。

### 环境确认

- Obsidian ≥ 1.5.0（务必检查：点击左下角齿轮 → General → 查看版本号，如果低于此版本请先在官方下载覆盖安装）
- 一个有效的 DeepSeek API Key（从 https://platform.deepseek.com 获取，新用户有免费额度）
- 一个已有至少十几篇笔记的测试 vault（如果没有，现在创建几篇内容不同的笔记，比如一篇讲学习 Python 的，一篇讲 Obsidian 插件的，一篇讲浏览器历史的）

### 安装 Smart Connections 并观察索引过程

1. **安装插件**：打开 Obsidian，进入 Settings → Community Plugins（确保 Safe Mode 已关闭），点击 Browse 搜索 “Smart Connections”。找到 `Smart Connections`（作者：Brian Petro），点击 Install 然后 Enable。
2. **定位索引文件**：安装并启用成功后，在系统文件管理器中进入你的 vault 根目录，打开路径 `.obsidian/plugins/smart-connections/`。暂不观察文件内容。
3. **触发首次索引**：重新启动 Obsidian（很重要：插件在启动时执行全量索引）。打开时你可能会注意到风扇加速和 CPU 占用升高，这是 JavaScript 的单线程正在执行密集的向量计算。如果你有大量笔记，这个过程可能会持续几十秒。
4. **检查索引生成**：索引完成后，再次查看 `.obsidian/plugins/smart-connections/` 文件夹下 JSON 文件（如 `data.json` 或 `smart-connections.json`）的大小。**如果你有几百篇笔记，这个文件会比初始安装时明显增大，从几十 KB 增长到数 MB 级别。** 打开此文件，你会看到类似以下的结构（原始 JSON 可能嵌套很深，建议用支持折叠的编辑器查看）：

```json
{
  "embeddings": {
    "file::some_hash_123": {
      "text": "原子化笔记的第一个段落内容...",
      "embedding": [0.012345, -0.023456, 0.034567, ...]
    }
  },
  "file_hashes": {
    "path/to/note.md": "hash_based_on_content"
  }
}
```

> **可观察证据**：对比安装前后的文件大小变化，确认索引确实被生成并持久化到了本地。

### 配置 DeepSeek API

Smart Connections 本身也可以配置云端 LLM 来回答问题，但为了让你更直接地理解 API 调用机制，我们先不使用它的内置聊天，而是安装一个**更透明的 Copilot 类型插件**（Smart Composer）来做测试。如果你已经有其他支持 API 密钥的 AI 插件（如 Text Generator 或 Copilot），配置逻辑是相似的。

1. **安装 Smart Composer**：同样在 Community Plugins 里搜索 “Smart Composer”（作者：Vadim Lobanov，确认插件 ID 是 `smart-composer`），安装并启用。
2. **打开插件设置**：进入 Settings → Community Plugins → Smart Composer → Options。
3. **配置 API 提供者**：
   - Model Provider：选择 `OpenAI Compatible`（注意非直接在列表里选 DeepSeek，而是用通用兼容接口）。
   - API Base URL：填入 `https://api.deepseek.com/v1`
   - API Key：填入你的 DeepSeek API Key
   - Model Name：手动输入 `deepseek-chat`
   - Context Window Size：填入 `128000`
4. **验证连接**：在 Smart Composer 设置里通常会有一个“Test Connection”或“Validate”按钮，点击测试。如果出现绿色的成功提示，说明配置正确。如果失败，检查 API Key、Base URL（严格确保 `/v1` 结尾）。

> **为什么用 OpenAI Compatible**：许多国产大模型（DeepSeek、Qwen、Moonshot）都开放了 OpenAI 兼容接口，意味着它们接受与 OpenAI 相同的 JSON 请求格式。这是目前 API 互操作性的事实标准。当你在下一步在第 4 章为 Ollama 配置相同的接口时，整个流程可以完全复刻，只改一个 URL。

### 第一次对话：用笔记内容提问

1. 打开一个内容较长的笔记（或者创建一个新笔记，写几段关于某个特定主题的文字，比如“咖啡豆的分类与冲泡方法”）。
2. 选中一段关于咖啡豆的文字。
3. 用快捷键呼出 Smart Composer 对话框（默认是 Ctrl/Cmd + Shift + Enter，查看插件设置确认快捷键）。
4. 在对话框中输入：“根据我选中文本的内容，总结一下这篇笔记关于咖啡豆的主要观点。”
5. 观察 AI 如何回应。

**你可能会立即收到模型回复**，这说明插件将你选中的文本和你的问题一起发送给了 DeepSeek API。**这里发生的事是**：插件构造了一条 HTTP POST 请求，把包含系统提示、你的笔记片段、你的问题的 JSON 数据，用 Content-Type: application/json 的方式发给了 `https://api.deepseek.com/v1/chat/completions`。服务器返回的流式数据通过 SSE 被插件接收并逐 token 显示在屏幕上。

## 动手观察：追踪数据流

现在你已经看到了 AI 插件工作的表象。接下来是“窥探黑盒”环节：用浏览器的开发者工具观察真实的网络请求。

1. **打开 Obsidian 开发者工具**：按 Ctrl+Shift+I（Windows/Linux）或 Cmd+Option+I（macOS）。
2. **切换到 Network 标签页**。
3. **勾选“Preserve log”**（保持日志），以防止请求在页面跳转时被清除。
4. **再次在 Smart Composer 中提出一个问题**。
5. **在 Network 面板中找到对 `chat/completions` 的 POST 请求**，点击查看详情。
6. **观察 Request Payload**：你会看到一个标准的 Chat Completions API 请求体，包含 `model`、`messages` 数组等字段。在 `messages` 里，`system` 消息是插件自动插入的指令（如“你是一个帮助用户整理笔记的助手”），`user` 消息则包含你选中的笔记内容和你的问题。
7. **切换到 Response 标签页**：如果你是流式输出模式，这个标签页显示的可能不是完整的 JSON 响应，而是多个 `data:` 推送块。这是 SSE 协议的直接证据。

> **可观察证据**：你在 Network 面板里看到了结构化的 HTTP 请求和响应。这不是黑盒魔法，而是一次标准的 REST API 调用。

## 故障排查

### 问题 1：Smart Connections 索引过慢或卡住

**表现**：打开 Obsidian 后 CPU 占用持续高负载，插件状态显示“索引中”但迟迟不完成。

**原因**：如果 vault 中笔记过多（数千篇以上），纯 JavaScript 的向量化流程可能非常缓慢。它也取决于你配置的 Embedding 模型速度。

**解决方法**：进入 Smart Connections 设置，找到“Excluded folders”（排除文件夹），将不重要的、大型的文件目录排除出索引范围。如果你使用了远程模型，暂时断开网络，插件会在本地尝试失败后跳过（但不会产生有用索引）。或者暂时禁用其他大量插件，为 Embedding 计算释放更多 CPU 和内存资源。

### 问题 2：Smart Composer 连接 DeepSeek 失败

**表现**：Test Connection 失败，或对话时提示错误。

**排查清单**：
1. **API Key 是否正确**：从 DeepSeek 管理后台重新复制，确保没有多余空格。
2. **API Base URL 是否正确**：必须是 `https://api.deepseek.com/v1`（注意是 `https`，结尾必须有 `/v1`）。
3. **账户余额**：登录 DeepSeek 平台检查 API 余额是否用尽。新用户的免费额度有时效和上限。
4. **网络环境**：如果你在需要代理访问外网的环境中，Obsidian 插件默认走系统代理。如果系统代理已关闭，插件也无法直接连接。检查系统网络设置，或为 Obsidian 所在的网络环境开放直连。

### 问题 3：插件回应时“胡编乱造”，与笔记毫无关系

**表现**：AI 给出的信息在你的笔记里完全找不到，明显是模型的“幻觉”。

**原因**：对于 Smart Composer，可能是你没有正确选中文本或 @ 引用文件，导致上下文为空，模型只能“自由发挥”。对于 Smart Connections，可能是索引尚未完全建立（仍在初始索引），或你提问的关键词与笔记内容在 Embedding 语义空间中距离太远。

**解决方法**：
- Smart Composer：确认你选中的文本或@的文件在问题窗口中可见（插件会显示聊天消息的上方展示了文件列表）。
- Smart Connections：在 Smart Connections 的搜索视图中先搜索试试，看是否返回了相关块。如果搜索也空，说明索引确实不包含相关内容，可能需要重新索引。

## 练习

### 练习一：识别插件模式

你的朋友安装了三个 Obsidian 插件：Smart Connections、Copilot、和 Text Generator。但他搞不清每个插件分别属于哪种工作模式。请用一句话描述他该如何判断一个 AI 插件属于“索引模式”还是“上下文模式”，而不需要查看源码。提供一种可以在 30 秒内验证的判断方法。

**预期成果**：一个清晰的判定规则。

### 练习二：追踪 API 请求特征

使用 Obsidian 的开发者工具（DevTools），向 Smart Composer 提问：“什么是原子化笔记？”如果这句话在你的知识库索引范围内，观察请求的 Network 面板。

1. 记录 `messages` 数组中有几个 `role: "user"` 条目。
2. 找出插件将你的系统提示设置为了什么内容（在 `role: "system"` 条目中）。
3. 如果你的知识库索引中存在原子化笔记的相关内容，它是通过哪个字段传递给 API 的？（提示：看 `user` 消息的内容，找没有引号和显式文本的块）

**预期成果**：一条截图或笔记，标出了系统提示和用户提示的内容，以及相关笔记片段出现的字段。

### 练习三：索引与更新机制的实验

创建一个名为 `Test Chunking` 的新笔记，写入以下内容并在每次操作间观察 `.obsidian/plugins/smart-connections/` 中 JSON 文件大小的变化：

1. 写文字“原子化笔记的第一部分。”保存并等待 1 分钟，检查 JSON 大小。
2. 添加第二段文字“这是独立的第二个想法，与第一部分无关。”保存并等待，再检查。
3. 将全部文字删除，保存并检查。

对比三次观察结果，解释为什么索引大小发生了变化，变化量是否与新增的文字量成正比？如果不完全成正比，可能的原因是什么？（要求给出合理推理，而非唯一正确答案）。

**预期成果**：三次文件大小的记录，以及一段对变化趋势的解释。

## 自检

1. 能否用 3 句话分别描述 Smart Connections 和 Copilot 系插件在自己提问到返回答案的全链路中，文件、网络、模型分别扮演了什么角色？
2. 如果你在 `.obsidian/plugins/smart-connections/` 下发现了巨大的向量存储文件，这份文件里最关键的三个字段是什么？它们的值分别代表什么？
3. 当你在 Smart Composer 里提问时，为什么 AI 可能不知道“你的知识库里还有哪些你没 @ 的文件”？试着从 Copilot 不预先索引这一事实出发解释。
4. SSE 流式输出和一次性返回的区别仅仅在“打字机效果”上吗？从网络连接的角度，SSE 在数据抵达客户端后对用户体验有什么根本性的改变？
5. Smart Connections 在启动时执行全量索引，假设你有 200 篇笔记，每篇分成 5 个块，每个块的 Embedding 请求需要 100ms。在理想条件和不考虑并发的前提下，整个索引过程需要多长时间？如果未来你的笔记数量增长到 2000 篇，索引时间会如何变化？这暗示了 Smart Connections 这类纯桌面端索引方案的什么规模限制？

## 参考文献

- [Smart Connections Obsidian Plugin - GitHub Repository](https://github.com/brianpetro/obsidian-smart-connections)（community）：社区维护的核心插件，展示文件监听、向量化和检索管线的完整实现。
- [Home - Obsidian Developer Documentation](https://docs.obsidian.md/Home)（official）：官方开发者文档，描述插件 API 生命周期、Vault 事件系统和插件的加载机制。
- [DeepSeek API Documentation](https://platform.deepseek.com/api-docs/)（official）：DeepSeek API 的官方使用指南，包括 OpenAI 兼容接口的配置参数和常见错误码。
- [OpenAI Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat)（official）：OpenAI Chat Completions API 参考，定义了所有云端兼容 API 的请求体结构和流式响应格式。
- [SSE Specification (Server-Sent Events)](https://html.spec.whatwg.org/multipage/server-sent-events.html)（standard）：WHATWG SSE 标准，定义服务端推送事件流的协议细节和客户端 API。
