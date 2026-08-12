# 第 4 章 全本地离线闭环——Ollama + 本地 Vector DB 部署

> 预计学习时间：90-120 分钟（含模型下载时间）。本章会先给出离线 RAG 的验收标准，然后按“硬件评估 → Ollama 安装 → Embedding 模型部署 → LLM 部署 → 集成 Smart Connections → 全离线验证”的顺序操作。每一步都有可观察的命令输出或界面结果；在模型下载期间，你可以阅读后面的必要原理讲解。
> 一句话总结：用 Ollama 在本地同时运行 Embedding 模型和对话模型，通过 OpenAI 兼容接口对接 Smart Connections 插件，实现在不联网的情况下完成笔记索引和 RAG 问答。

## 一、先看本章完成后的结果

在动手之前，先明确完成标准。本章结束时，你的电脑应能同时做到以下四点：

1. 在终端执行 `ollama list`，输出的模型列表中同时包含一个 Embedding 模型（如 `bge-m3` 或 `nomic-embed-text`）和一个对话模型（如 `qwen2.5`）。
2. 在终端用 `curl` 向 `http://localhost:11434/v1/embeddings` 发送一段文本，得到一个浮点数数组形式的嵌入向量。
3. 在终端用 `curl` 向 `http://localhost:11434/v1/chat/completions` 提问，得到以流式 token 返回的完整回答——与第 3 章调用 DeepSeek API 时的响应格式完全一致。
4. 在 Smart Connections 插件中将“嵌入模型”和“对话模型”的提供商都切换为“本地 Ollama”，**断开网络后仍能完成笔记索引和 RAG 问答**。

四个结果缺一不可。1 和 2 验证 Embedding 链路——笔记能否被转换成可供检索的向量；3 和 4 验证对话链路——提问能否在不联网的情况下得到基于本地笔记的回答。

## 二、为什么需要一套全离线的本地 RAG

第 3 章已经跑通了端到端 RAG，但所有数据——笔记的嵌入向量和你向 AI 提出的问题——都经过了 DeepSeek 的服务器。这在以下场景中会出问题：

- **隐私敏感内容**：日记、项目机密、医疗或财务笔记，按合规要求不应上传到第三方 API。
- **网络不可靠环境**：飞机上、会议室屏蔽网络、服务器机房内，不能依赖云端 API。
- **完全自主控制**：更换模型版本、调整推理参数、彻底删除数据，自己做主。

本地 RAG 解决这些问题的核心思路是：把云端那套 API 原样搬到自己的电脑上。Ollama 在本地提供与 OpenAI 格式兼容的 HTTP 接口；Smart Connections 不关心请求是发给本地进程还是云端——这正是第 3 章结束时“bridge_to_next”的目标。

> **为什么需要两个模型**
> 
> 第 3 章用 DeepSeek 同时充当了 Embedding 和对话模型，因为 DeepSeek 的 `deepseek-chat` 恰好两者都支持。但到本地部署时，这两个角色必须由**两个不同的模型**承担：
> - **Embedding 模型**把文本转成向量，追求高召回精度和多语言支持；
> - **对话模型**（LLM）负责理解问题、组织回答。
> 
> Ollama 会同时运行这两个模型，Smart Connections 在需要做向量索引时调用前者，在需要做 RAG 对话时调用后者。本章会逐一部署。

## 三、部署前评估：你的电脑能跑什么模型

在下载十几 GB 的模型文件之前，需要先评估你的硬件。这一节只有两个决定要做：**选 Embedding 模型** 和 **选对话模型的参数规模**。

### 3.1 认识 GGUF 格式与量化

本地模型文件的常见格式是 **GGUF**：一种专门为本地推理设计的文件格式，支持在普通 CPU 上高效运行，也支持将部分计算卸载到 GPU。下载文件时看到的 `q4_K_M`、`q8_0` 等标签，表示模型的“量化”级别。

- **量化**：可以理解为对原始模型做“有损压缩”。训练好的模型内部存储了大量高精度权重，量化后把每个权重从 16 位浮点数压缩到 4 位或 8 位整数，文件变小、运行更快，但推理质量略有下降。
- 本章选择 `q4_K_M` 作为默认推荐：它通常在质量损失非常小的情况下显著降低显存和内存占用，适合大多数 8 GB 及以上内存的设备。

Ollama 会自动从它的模型库拉取合适的量化版本，你不用手动挑选量化文件，只需指定模型名和参数大小即可。

### 3.2 Embedding 模型选型

Embedding 模型大小通常在几百 MB 到 2 GB 之间，即使是老旧设备也能轻松运行。本章提供两个选择：

| 模型 | 特点 | 适用场景 | 下载体积（约） |
| --- | --- | --- | --- |
| `nomic-embed-text` | 轻量级，仅支持英文 | 知识库以英文为主，设备内存紧张 | ~270 MB |
| `bge-m3` | 多语言、长文本（支持 8192 token），目前中文社区的事实标准 | 知识库包含中英文混排，追求高召回 | ~1.2 GB |

**本章默认选择 `bge-m3`**，因为它对中文笔记的语义区分能力远超纯英文模型。如果你在本章中途发现内存不足（Embedding 阶段通常不会），可以随时换回 `nomic-embed-text`——切换 Embedding 模型需要**重建整个向量索引**，Smart Connections 中有一键按钮。

### 3.3 对话模型选型

对话模型是真正的资源消耗大户。下面是几款在 Ollama 上可用的模型及其硬件需求，按推荐度排序：

| 模型 | 参数规模 | 推荐量化 | 最低内存 | 推荐内存 | 中文能力 |
| --- | --- | --- | --- | --- | --- |
| `qwen2.5:7b` | 7B | q4_K_M | 8 GB | 16 GB | 强，通义千问家族 |
| `qwen2.5:3b` | 3B | q4_K_M | 4 GB | 8 GB | 中上 |
| `deepseek-r1:7b` | 7B | q4_K_M | 8 GB | 16 GB | 强，但思考链较长 |
| `qwen2.5:14b` | 14B | q4_K_M | 16 GB | 32 GB | 强，回答质量显著提升 |

**内存足够（16 GB 及以上）时选 `qwen2.5:7b`；内存只有 8 GB 时选 `qwen2.5:3b`。** 7B 虽然听起来大，但量化后实际运行时占用大约 5-6 GB 内存，操作系统和 Obsidian 仍能正常运行。

Ollama 在 Windows 和 macOS 上都默认使用 **CPU 推理**，不需要独立显卡。如果你有 NVIDIA 显卡且显存 ≥ 6 GB，Ollama 会自动检测并启用 GPU 加速，速度快 5-10 倍。没有独显不影响完成本章目标，只是每次回答的等待时间会长一些（通常在 30 秒到 2 分钟之间）。

## 四、安装 Ollama

Ollama 是本章唯一需要从网络下载的软件。它是一个本地大模型运行工具，提供了从模型下载、推理到 API 暴露的完整功能。后续的 Embedding 和对话模型都由它托管，Smart Connections 只和它对话。

### 4.1 下载与安装

1. 打开 Ollama 官方下载页（见本章参考文献）。
2. 网站会自动识别你的操作系统。macOS 用户下载 `.dmg` 文件，双击后把 Ollama 图标拖入 Applications 文件夹；Windows 用户下载 `.exe` 安装程序，双击后按默认选项完成安装。
3. 安装完成后，macOS 的顶部菜单栏和 Windows 的系统托盘会出现一个羊驼图标。这表明 Ollama 以后台服务形式运行。

### 4.2 验证 Ollama 运行状态

打开终端（macOS：终端应用；Windows：PowerShell 或命令提示符），执行：

```bash
ollama --version
```

输出应显示类似 `ollama version 0.x.x` 的版本号。截至本章核验日期（2025 年 7 月），稳定版为 0.6.x 系列，任何这个范围以内的版本都能继续。

接着确认服务进程在运行：

```bash
ollama ps
```

如果输出为空（仅显示表头 `NAME    ID    SIZE    PROCESSOR    UNTIL`），说明服务正常但暂未加载模型——这是正常的。如果提示连接错误，说明后台服务未启动：macOS 在 Applications 中手动启动一次 Ollama.app；Windows 在开始菜单找到 Ollama 并启动。

> **Ollama 与模型的存储位置**
> 
> Ollama 下载的模型存储在用户目录下，默认位置为：
> - macOS：`~/.ollama/models/`
> - Windows：`C:\Users\<用户名>\.ollama\models\`
> 
> 不要在资源管理器中手动删除或移动这些文件；如需清理，使用 `ollama rm 模型名` 命令。

### 4.3 如果遇到网络较慢

Ollama 的模型文件托管在境外服务器，国内下载可能较慢。如果你的下载速度持续低于 1 MB/s，可以配置代理后重启 Ollama：

- macOS：在终端执行 `launchctl setenv HTTP_PROXY "http://127.0.0.1:你的代理端口"`，然后从 Applications 重新启动应用。
- Windows：在系统环境变量中设置 `HTTP_PROXY` 和 `HTTPS_PROXY` 为代理地址，然后重启服务。

如果完全没有代理，可以选择在模型拉取期间继续阅读后续章节的解释内容——拉取命令会持续运行，等讲解读完，模型可能已经下载好。

## 五、拉取并验证 Embedding 模型

现在拉取第一章 Embedding 模型。本课程以 `bge-m3` 为例；若你确定知识库以英文为主，把命令中的 `bge-m3` 替换为 `nomic-embed-text` 即可。

### 5.1 拉取模型

在终端执行：

```bash
ollama pull bge-m3
```

Ollama 会逐层下载模型文件，输出类似：

```text
pulling manifest
pulling 1234abcde... 100% ▕█████████████████▏ 1.2 GB
pulling 5678fghij... 100% ▕█████████████████▏ 12 KB
...
verifying sha256 digest
writing manifest
success
```

出现 `success` 表示拉取完成。**下载期间不要关闭终端。**

### 5.2 验证模型存在

```bash
ollama list
```

输出中应看到：

```text
NAME          ID              SIZE      MODIFIED
bge-m3:latest 1234abcde567    1.2 GB    刚刚
```

`SIZE` 列显示约 1.2 GB，与预期一致。如果显示较小或没有该条目，重新执行 `ollama pull bge-m3`。

### 5.3 动手测试 Embedding 接口

Embedding 模型拉取完成后，可以立即验证它能否正确生成向量。Ollama 自动在 `http://localhost:11434` 上暴露了 OpenAI 兼容的 Embedding 端点。用 `curl` 发送一段测试文本：

**macOS 与 Linux：**

```bash
curl http://localhost:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-m3",
    "input": "Obsidian 是一款本地优先的知识管理工具"
  }'
```

**Windows PowerShell：**

```powershell
curl http://localhost:11434/v1/embeddings -H "Content-Type: application/json" -d "{`"model`": `"bge-m3`", `"input`": `"Obsidian 是一款本地优先的知识管理工具`"}"
```

> **⚠️ Windows 用户请注意：PowerShell 中的 `curl` 不是原生 cURL**
> 
> PowerShell 内置的 `curl` 实际上是 `Invoke-WebRequest` 的别名，它解析参数的方式与真正的 cURL 不同。执行上面的 PowerShell 版命令可能会失败，或只显示 HTTP 响应对象而非 JSON 内容。你有两种解决方法：
> 
> 1. **使用 `curl.exe`（推荐）**：Windows 10 1803 及以上版本自带真正的 cURL，路径为 `C:\Windows\System32\curl.exe`。把命令中的 `curl` 替换为 `curl.exe`，其余参数与 macOS 版完全相同（不用转义引号）：
>    ```powershell
>    curl.exe http://localhost:11434/v1/embeddings -H "Content-Type: application/json" -d '{"model":"bge-m3","input":"Obsidian 是一款本地优先的知识管理工具"}'
>    ```
> 2. **使用 `Invoke-RestMethod`**：PowerShell 原生的 REST 客户端，无需任何转义：
>    ```powershell
>    Invoke-RestMethod -Uri http://localhost:11434/v1/embeddings -Method Post -Headers @{"Content-Type"="application/json"} -Body '{"model":"bge-m3","input":"Obsidian 是一款本地优先的知识管理工具"}'
>    ```
> 
> 本章后续所有涉及 `curl` 的 Windows 命令，均请自行替换为 `curl.exe` 或 `Invoke-RestMethod`，正文不再逐条重复此提示。

无论哪个系统，成功响应会返回一个 JSON，其中 `data[0].embedding` 字段是一个浮点数数组，长度通常为 1024（这是 `bge-m3` 输出维度）。你会看到类似这样的长串数字：

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "index": 0,
      "embedding": [0.0123, -0.0456, 0.0789, ...]
    }
  ],
  "model": "bge-m3",
  "usage": { "prompt_tokens": 8, "total_tokens": 8 }
}
```

**如果你只看到前几个数字后面是省略号 `...`，这是 curl 输出过长时终端的显示截断，不是错误。** 在 `curl` 命令末尾加上 `| head -c 200` 可以只看开头。

如果命令返回 `curl: (7) Failed to connect to localhost port 11434`，说明 Ollama 服务未运行（参考 4.2 节启动它）；如果返回模型未找到的信息，检查 `ollama list` 确认模型名和拉取完成状态。

### 5.4 bge-m3 为什么成为中文社区的标准选择

理解 Embedding 模型的选择逻辑有助于排查后续问题。`bge-m3` 由北京智源人工智能研究院（BAAI）发布，有三个特点：

- **多语言**：训练数据同时覆盖中英文，对中文语义的理解远超只用英文训练的模型。
- **长上下文**：支持最长 8192 token 输入。大部分笔记可以整篇送入，无需在 Embedding 阶段做分块。
- **稠密+稀疏双表示**：`bge-m3` 同时输出稠密向量（用于向量相似度搜索）和稀疏词权重（可用于 BM25 关键词搜索）。本章目前只使用稠密向量部分，稀疏能力为第 5 章的混合检索提供了基础。

如果未来的某天你需要处理更长文档或有其他语种需求，Ollama 上的 `mxbai-embed-large`、`nomic-embed-text` 等模型均可按相同方式拉取和切换。

## 六、拉取并验证对话模型

现在拉取对话模型。本课程以 `qwen2.5:7b` 为例；若你的内存只有 8 GB，请替换为 `qwen2.5:3b`。

### 6.1 拉取模型

```bash
ollama pull qwen2.5:7b
```

这次下载的量会大得多——量化后的 7B 模型约 4.5 GB。耐心等待 `success` 出现。注意：**下载期间不要关闭终端**，你可以把终端窗口放在后台，在本章文字中继续往下读。

### 6.2 验证模型存在

```bash
ollama list
```

此时应看到两个模型：

```text
NAME            ID              SIZE      MODIFIED
bge-m3:latest   1234abcde567    1.2 GB    几分钟前
qwen2.5:7b      9876fedcba98    4.5 GB    刚刚
```

### 6.3 在终端直接对话测试

在拉取完成后，直接在终端测试对话：

```bash
ollama run qwen2.5:7b
```

终端会进入交互模式，提示符变为 `>>> `。输入一句问候：

```text
>>> 你好，请用一句话介绍你自己
```

模型会逐字输出回答。回答结束后，输入 `/bye` 退出交互模式。

如果此步顺利完成，说明对话模型可以在本机推理。相比第 3 章调用云端 API，这里的响应速度明显更慢——在纯 CPU 的 MacBook Air 上可能每秒输出 3-8 个 token——这是正常的。如果你有 NVIDIA 显卡且 Ollama 启用了 GPU 加速，速度会接近云端。

### 6.4 根据硬件实际情况调整

如果 `ollama run qwen2.5:7b` 执行后：

- **系统变得非常卡顿**：内存不足，Ollama 正在使用硬盘交换空间。执行 `ollama rm qwen2.5:7b` 删除它，改为 `qwen2.5:3b`。
- **回答速度很快（≥30 token/秒）**：说明 GPU 在工作，你可以尝试更大的模型 `qwen2.5:14b` 获得更高质量的回答。
- **回答乱码或中英混杂**：检查模型名是否正确。`qwen2.5:7b` 是中文优化的通义千问系列；如果误用了英文模型（如 `llama3.2`），对中文笔记的理解会差很多。

Windows 用户注意：如果内存只有 8 GB，Ollama 拉取 7B 模型时可能触发 Windows 的警告弹窗，直接中止下载，改用 3B 模型即可。

## 七、验证 OpenAI 兼容的 Chat Completions 端点

第 3 章接入 DeepSeek 时，Smart Composer 实际是在向 `https://api.deepseek.com/v1/chat/completions` 发送请求，请求体格式完全遵循 OpenAI 规范。现在 Ollama 已经在 `http://localhost:11434/v1/chat/completions` 暴露了格式完全相同的端点。

用 `curl` 测试它：

**macOS：**

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5:7b",
    "messages": [
      {"role": "user", "content": "Obsidian 的双链功能与普通超链接有什么本质不同？请用一句话回答。"}
    ],
    "stream": false
  }'
```

**Windows PowerShell（请遵照 5.3 节提示，使用 `curl.exe` 或 `Invoke-RestMethod`，此处仅给出对应的 curl.exe 命令）：**

```powershell
curl.exe http://localhost:11434/v1/chat/completions -H "Content-Type: application/json" -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"Obsidian 的双链功能与普通超链接有什么本质不同？请用一句话回答。"}],"stream":false}'
```

`"stream": false` 表示要求一次性返回完整结果，便于查看。成功返回的 JSON 中，`choices[0].message.content` 字段包含模型的回答。

这个请求格式与第 3 章发送到 DeepSeek 的请求完全对应——相同的 `model` 字段结构，相同的 `messages` 数组，相同的 `choices` 路径提取回答。唯一的区别是 URL 从 `https://api.deepseek.com/v1` 变成了 `http://localhost:11434/v1`，以及 `model` 从 `deepseek-chat` 变成了 `qwen2.5:7b`。

**这个一致性很关键**：Smart Connections 和所有支持 OpenAI 格式的插件，在本章不需要任何代码层面的适配，只需要在设置界面中改两个字段——API 地址和模型名。

## 八、把本地服务接入 Smart Connections

从本节开始，所有操作都在 Obsidian 中进行，并且与第 3 章部署 Smart Connections 的经验直接衔接。

### 8.1 确保 Smart Connections 已安装

如果你的 Vault 中还没有安装 Smart Connections：

1. 打开 Obsidian → 设置（齿轮图标）→ 第三方插件 → 关闭安全模式。
2. 点击“浏览”搜索 **Smart Connections**，作者为 Brian Petro。
3. 安装并启用插件。

如果你已经跟随第 3 章安装了 Smart Connections，此时左侧边栏应该已有“Smart Connections”图标（一个带箭头的聊天气泡），并且在 `.obsidian/plugins/smart-connections/` 下可以找到向量存储文件。

### 8.2 配置本地 Embedding 模型

1. 打开 Obsidian 设置 → 第三方插件 → Smart Connections → 点击齿轮图标进入插件设置。
2. 在 **Embedding Model** 部分：
   - 将“提供商”或“API Provider”切换到 **Custom** 或 **Local**（不同版本名称略有不同，选择非 OpenAI/Anthropic 的本地选项）。
   - 在 **API URL** 或 **Base URL** 字段中填写：`http://localhost:11434/v1`
   - 在 **Model** 或 **Embedding Model Name** 字段中填写：`bge-m3`
   - **API Key** 字段留空或填 `ollama`（Ollama 服务不需要密钥，但有些插件要求此字段非空）。
3. 点击下方的 **Test** 或 **Verify** 按钮（如果有）。插件会发送一条测试请求到 `http://localhost:11434/v1/embeddings`，并检查返回向量维度是否正确。
4. 如果测试成功，保存设置。

### 8.3 配置本地对话模型

1. 在同一个设置页面，找到 **Chat Model** 或 **Completion Model** 部分。
2. 同样选择 **Custom** 或 **Local** 提供商。
3. **API URL** 填写：`http://localhost:11434/v1`
4. **Model** 填写：`qwen2.5:7b`（或你选择的版本，如 `qwen2.5:3b`）。
5. **API Key** 同样留空或填 `ollama`。
6. 测试并保存。

### 8.4 强制重建向量索引

切换 Embedding 模型后，必须从头重建索引，因为新的 Embedding 模型生成的向量维度和语义空间与旧的完全不同（第 3 章使用的可能是 DeepSeek 的 Embedding 端点，现在变成了 `bge-m3` 的 1024 维）。混合使用不同维度的向量会导致检索功能异常或崩溃。

在 Smart Connections 设置中找到 **Force Re-index** 或 **Rebuild Index** 按钮，点击后确认。插件会遍历 Vault 中所有 Markdown 文件，逐一发送到 Ollama 的 Embedding 端点，然后把返回的向量写入本地存储。

索引过程中：

- 打开 Obsidian 开发者工具（Cmd/Ctrl + Shift + I），切换到 **Console** 面板，可以看到每个被索引文件的日志。
- 终端执行 `ollama ps`，会显示 `bge-m3` 正在被使用，且状态为 `running`。
- 索引速度取决于笔记数量和 CPU 性能。每篇笔记的 Embedding 时间通常在 0.3-2 秒之间；100 篇笔记的 Vault，全量重建大约需要 1-3 分钟。

**索引期间保持 Obsidian 打开，不要同时编辑正在被索引的笔记**，否则插件可能捕获到修改事件并引发重复索引。

### 8.5 对比验证：本地索引 vs 云端索引

索引完成后，在 Smart Connections 面板中提问一个与你的笔记内容相关的问题，例如：

> “我的知识库中关于【某个你已记录的Topic】有哪些主要观点？”

模型应返回基于笔记内容的回答。此时观察：

- 点击回答下方的“显示上下文”或“Used Notes”按钮，应能看到 Smart Connections 检索到的相关笔记文件名和片段——这证明本地 Embedding 检索链路工作正常。
- 回答的质量应与第 3 章中云端模型的回答可比，但可能在逻辑严谨度上略有差距——这是本地小模型与 DeepSeek 旗舰模型之间的预期差异。第 5 章会通过混合检索和重排序来缩小这一差距。

如果回答与你的笔记无关、胡编乱造，或是直接报错，跳到本章“故障排查”一节。

## 九、全离线验证：断网测试

本章的核心目标是确保数据完全保留在本地，因此必须用断网测试来验证。

### 9.1 执行断网测试

1. **彻底断开网络连接**：关闭 Wi-Fi、拔掉网线、或开启飞行模式。不要只关闭浏览器，要确保整个操作系统无法访问外部网络。
2. 回到 Obsidian，在 Smart Connections 面板中提问一个新问题（不要重复刚才问过的，模型可能缓存了结果）。
3. 观察回答是否仍然正常返回。

如果断开网络后：

- ✅ **Chat 仍然给出基于笔记的回答**：全离线闭环成功。Embedding 检索（纯本地文件读取 + 向量计算）和 LLM 推理（Ollama 本机进程）都不需要网络。
- ❌ **提示连接错误或超时**：插件仍试图请求云端 API。回到设置页，确认 Chat Model 的 API URL 确实是 `http://localhost:11434/v1` 而非任何 `https://api.*` 地址。
- ❌ **回答成功但与笔记无关**：检索链路可能出问题了。检查 Console 是否有 Embedding 相关错误，回到 8.4 节确认向量索引重建完成。

### 9.2 断网测试通过意味着什么

现在你拥有了一个完全在本机运行的 RAG 系统：笔记文本、向量、权重和推理都在这台电脑上。即使在离线环境中，你也能向自己的知识库提问并获得基于笔记的回答。

恢复网络连接后，Smart Connections 的行为与断网时完全一致——Ollama 始终在 `localhost` 处理请求，网络连接对它没有影响。

## 十、故障排查：按依赖链从外到内

本地环境的复杂度高于纯云端配置，问题往往由多个层级叠加而成。排查时遵循“进程 → 模型 → 接口 → 插件”的顺序，每次只改变一个变量，记录结果后再进入下一层。

### 10.1 Ollama 服务不可达

**现象**：任何 `curl http://localhost:11434/...` 命令返回 `connection refused`。

**排查**：

```bash
# 确认 Ollama 进程状态
ollama ps
```

如果此命令也报错，说明 Ollama 后台服务未运行。macOS 从 Applications 启动 Ollama；Windows 从开始菜单启动或执行 `ollama serve` 手动启动。

如果 `ollama ps` 正常工作但 `curl` 仍然被拒，检查是否有防火墙拦截本地 11434 端口。**Windows 用户在首次启动 Ollama 时，可能会弹出防火墙提示，必须选择“允许访问”或“允许专用网络”。**

### 10.2 模型未找到

**现象**：`curl` 返回 “model 'bge-m3' not found”。

**排查**：

```bash
ollama list
```

确认模型已在列表中。如果不在，重新 `ollama pull` 并等待 `success`。如果模型在列表中但调用仍报错，检查模型名是否完全一致（区分大小写，带不带 `:latest` 标签都可能造成不匹配）。Ollama 的模型名以 `ollama list` 显示为准，不要在 `curl` 请求中编造版本号。

### 10.3 Embedding 接口正常但插件不工作

**现象**：`curl` 可以正常获取向量，但 Smart Connections 提示 Embedding 测试失败。

**排查**：

- 确认插件设置中的 Model 名称与 `ollama list` 输出完全一致，包括 `:latest` 后缀。
- 在浏览器中直接访问 `http://localhost:11434/`，如果看到 “Ollama is running”，说明服务端口正常。
- 打开 Obsidian 开发者工具 → Console，查看插件测试时的具体错误信息。

### 10.4 Chat 回答乱码或无视笔记内容

**现象**：回答语法混乱、中英掺杂、或明显在“背稿”而非基于检索到的笔记。

**排查顺序**：

1. **先确认对话模型是否选对**：在终端执行 `ollama run qwen2.5:7b "Obsidian是什么？一句话回答"`，观察输出质量。如果终端中的回答也乱码，说明模型本身不合格——可能是下载中断、文件损坏，执行 `ollama rm qwen2.5:7b && ollama pull qwen2.5:7b` 重新拉取。
2. **终端回答正常但插件回答无视笔记**：问题出在检索层，而非对话层。回到 Smart Connections 面板，提问后点击“显示上下文”，检查检索到的笔记片段是否确实与你问的主题相关。如果检索到的片段风马牛不相及，回到 8.4 节确认索引已重建。
3. **检索正确但模型仍然编造**：本地 7B/3B 模型的知识储备和推理能力有限。如果笔记片段本身信息量少或有歧义，小模型可能编造内容来“圆”回答。第 5 章的 Re-ranking 和更精准的片段召回可以改善这一问题。

### 10.5 索引速度极慢或卡住

**现象**：Smart Connections 索引进度条长时间不前进，或单个文件处理超过 10 秒。

**排查**：

- 在终端执行 `ollama ps` 确认 `bge-m3` 模型仍在运行。如果列表为空，Ollama 可能因内存不足而卸载了模型（这种情况下通常 Console 会有“model not loaded”错误）。尝试重启 Ollama 并重新触发索引。
- 极少数笔记文件如果包含大量非文本内容（如嵌入的 Base64 图片），可能导致 Embedding 请求过载。检查 Vault 中是否有特别大的 `.md` 文件（超过 1 MB），暂时移出 Vault 完成索引后再移回。

## 十一、本章验收记录

完成本章后，填写下面的核验表。每一项都需要有直接的观察结果支持，不要凭感觉勾选。

| 核验项 | 你的结果 | 检查方法 |
| --- | --- | --- |
| Ollama 版本 | | `ollama --version` |
| Embedding 模型在列表中 | | `ollama list` 含 `bge-m3` |
| 对话模型在列表中 | | `ollama list` 含 `qwen2.5:7b` 或你选择的版本 |
| Embedding 端点返回向量 | | `curl http://localhost:11434/v1/embeddings` 返回 `embedding` 数组 |
| Chat 端点返回回答 | | `curl http://localhost:11434/v1/chat/completions` 返回 `choices[0].message.content` |
| Smart Connections Embedding 测试通过 | | 插件设置页中 Test/Verify 按钮提示成功 |
| Smart Connections Chat 设置完成 | | 设置页中 API URL 为 `http://localhost:11434/v1` |
| 向量索引已重建 | | Console 中看到各文件索引日志，或索引进度条完成 |
| **断网后 RAG 问答成功** | | **关闭 Wi-Fi，Smart Connections 仍能基于笔记回答** |

最后一行“断网后 RAG 问答成功”是本章必须通过的硬性标准。如果没有达成，请对照故障排查节查找原因，直到显示“成功”再进入第 5 章。

## 十二、本章回顾

你已经把第 3 章的云端 RAG 链路完整地迁移到了本地。现在笔记本上的 Markdown 文件在需要时被转换成向量存入本地索引，你的提问在本地被转成向量去匹配那些片段，再由本地运行的对话模型整合成回答——整个过程没有一个字节离开这台电脑。

回顾第 2 章的原子化笔记和 YAML Frontmatter，它们在这一章首次在“离线环境”中被加载到语义检索系统中，成为可被查询的知识单元。接下来第 5 章将直面目前这套纯向量检索的局限——专有名词、代码片段和英文缩写仍可能被漏掉——并引入关键词搜索和重排序来弥补这些不足。

## 参考文献

- Ollama. [Ollama 官方下载页](https://ollama.com/download).
- Ollama. [OpenAI Compatibility 文档](https://docs.ollama.com/api/openai-compatibility).
- BAAI. [bge-m3 模型说明页](https://huggingface.co/BAAI/bge-m3).
- Alibaba Cloud. [Qwen2.5 模型系列](https://huggingface.co/Qwen).
- Brian Petro. [Smart Connections 插件文档](https://github.com/brianpetro/obsidian-smart-connections).
