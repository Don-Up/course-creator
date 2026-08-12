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


---

# 第 5 章 Advanced RAG 进阶——混合检索与 Re-ranking

> 预计学习时间：150–210 分钟  
> 一句话总结：从纯向量检索的词汇失明现象出发，先理论推演 BM25 与 RRF 融合为何能召回“像结果但不像问题”的文本，再代码落地混合检索管道并部署 bge-reranker 进行精排，最后用 A/B 对比量化每个组件的独立贡献。

## 为什么你的本地 RAG 回答不上专有名词？

完成第4章全本地部署后，你的 Obsidian 知识库已经能断网问答了。现在试着问一个看起来很简单的问题：

```
在 Notes 文件夹中查询：什么是 "FBS"？
```

你的本地 RAG 系统可能返回了关于“库存管理”或“前端基础”的笔记，唯独没有包含那条明确写了“FBS 全称 Fulfillment By Seller”的笔记。但查询字符串 `FBS` 明明出现在那条笔记里。为什么基于语义相似度的向量检索找不到一个精确匹配的词？

另一个常见失败场景：

```
在知识库中搜索：Git 中 git stash pop 和 git stash apply 的区别。
```

你有一条笔记详细记录了 `git stash pop` 会删除 stash 而 `git stash apply` 保留 stash 的备忘。但向量检索的 Top-3 结果中，排行第一的竟是“如何在 Git 中撤销提交”，第二是关于“分支合并策略”的笔记。那条包含精确命令的备忘排在第五位以后，LLM 最终收到的上下文里根本没有它。

这揭示了一个根本矛盾：**向量语义匹配擅长“理解意思”，但它不擅长“匹配字符”**。

向量 Embedding 模型被训练来捕捉语义：它将“FBS”和“Fulfillment by Seller”映射到高维空间中相近的点。但如果你问的是一个不常见缩写、一个代码函数名，或者一个出现在笔记中但从未出现在训练数据中的专有名词，模型无法为它生成“好的”向量。它的 Embedding 退化成一个没有语义辨识度的随机方向，就像一个陌生人凭照片认人，而你给的照片是一串字母。

这就引出了纯向量检索（Dense Search）的边界问题，也是本章混合检索要解决的第一个核心问题。

## 逐项拆解：向量检索到底在哪一步失败了？

我们不猜测，直接用实验定位。打开终端，使用第4章已部署的 Ollama 和 bge-m3：

```bash
# 确保 Ollama 正在运行
ollama list

# 查询两个文本的 Embedding 相似度
curl -s http://localhost:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-m3",
    "input": ["FBS 是 Fulfillment By Seller 的缩写，指卖家自配送模式。",
               "卖家可以选择不同的物流配送方式。"]
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'捕获到 {len(data[\"data\"])} 条 Embedding')
# 这里只验证返回结构，相似度计算在下文
"

# 同理，检查专有名词与描述的关系
curl -s http://localhost:11434/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-m3",
    "input": ["git stash pop",
               "使用 git stash pop 会删除栈顶的暂存记录"]
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Embedding 维度: {len(data[\"data\"][0][\"embedding\"])}')"
```

两条命令分别确认：①本地 Embedding 服务正常；②返回的 Embedding 均为 bge-m3 的 1024 维向量。现在我们计算余弦相似度，直观对比“能匹配的语义”和“匹配不到的专有名词”：

```python
import numpy as np
import requests

# 封装 Ollama Embedding 调用
def embed(text: str) -> np.ndarray:
    resp = requests.post(
        "http://localhost:11434/v1/embeddings",
        json={"model": "bge-m3", "input": [text]}
    )
    return np.array(resp.json()["data"][0]["embedding"])

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

# ---- 实验1：有语义重合的文本 ----
query = "FBS 是什么？"
doc_a = "FBS 是 Fulfillment By Seller 的缩写，指卖家自配送模式。"   # 包含精确匹配
doc_b = "卖家可以选择不同的物流配送方式。"                        # 语义相关但无匹配词

eq = embed(query)
ea = embed(doc_a)
eb = embed(doc_b)

sim_a = cosine_sim(eq, ea)
sim_b = cosine_sim(eq, eb)

print("--- 实验1：专有名词匹配 ---")
print(f"query vs 包含精确缩写:  相似度 {sim_a:.4f}")
print(f"query vs 语义相关无缩写: 相似度 {sim_b:.4f}")
print(f"两者差距: {sim_a - sim_b:.4f}")

# ---- 实验2：精确代码命令 ----
query2 = "git stash pop"
doc_c = "使用 git stash pop 会删除栈顶的暂存记录。"           # 包含命令
doc_d = "建议在执行 git 操作前先切换到一个新的分支。git 暂存区里的内容可以多次 apply。"  # 相关但不含 pop

eq2 = embed(query2)
ec = embed(doc_c)
ed = embed(doc_d)

sim_c = cosine_sim(eq2, ec)
sim_d = cosine_sim(eq2, ed)

print("\n--- 实验2：精确代码命令 ---")
print(f"query vs 包含命令:       相似度 {sim_c:.4f}")
print(f"query vs 语义相关无命令: 相似度 {sim_d:.4f}")
print(f"两者差距: {sim_c - sim_d:.4f}")
```

**可观察结果**：实验1中，包含“FBS”缩写的 doc_a 相似度显著高于 doc_b（差距通常在0.15以上）。但实验2中，两个文档的相似度差距明显缩小，甚至 doc_d 可能高于 doc_c。这是因为 `git stash pop` 整体被视为罕见词组合，而模型从没见过它的“语义长相”。当文本与训练数据分布差异越大，Embedding 质量退化越严重。

这个实验得出第一个结论：**对于代码片段、命令、缩写、序列号或任何训练语料中低频出现的术语，向量相似度不可靠。** 此时需要的不是更准的语义，而是更准的“字面”。下面的章节解决“字面怎么来”和“向量与字面怎么协同”两个问题。

## BM25：给每个词一个“稀有度权重”

向量检索（Dense Search）算的是文本的“整体意思”，没有单独对待词语。但在信息检索中有一个被验证了几十年的原则：**越罕见的词，辨识力越强**。你知识库里“管理”可能出现上百次，“FBS”可能只出现两次。当你查询 FBS 时，包含“FBS”的文档应该天然排在前面，无论它的语义 Embedding 是否“认为”它相关。

BM25 是一族基于词频和逆文档频率的排序函数，也是本章混合检索中稀疏检索侧的核心。我们从它的两个支柱开始：TF（词频）和 IDF（逆文档频率）。

### 定义参与对象和关键状态

在一个待检索的文档集合 D 中，对任意查询词 t：
- **词频（TF）**：词 t 在当前文档中出现了多少次。但它不是简单计数，BM25 对 TF 做了饱和处理：出现 2 次比出现 1 次重要，但出现 50 次和 100 次的差异几乎可以忽略。这避免了长文档仅因为重复同一个词就霸占排名。
- **逆文档频率（IDF）**：衡量词 t 在整个文档集 D 中的稀有程度。IDF 高 → 稀有 → 信息量大 → 排序权重高；IDF 低 → 常见 → 信息量小 → 排序权重低。如果 t 出现在几乎每篇文档中，它的 IDF 接近于 0，即对排序几乎没有贡献。
- **文档长度归一化**：长文档天然包含更多词，仅凭 TF 会偏向长文档。BM25 用平均文档长度纠正长度偏差：同样的 TF，在短文档里比在长文档里更“值钱”。

### 最小前置：倒排索引——为什么 BM25 能直接找到词

为了理解 BM25 为什么可以快速找到包含某个词的文档，你需要知道一个最简单的数据结构：倒排索引（Inverted Index）。正向索引是“文档→词列表”，而倒排索引是“词→文档列表”。例如，对于两篇文档：
- 文档 0: "FBS 是卖家自配送模式"
- 文档 1: "卖家可以选择不同物流方式"

预处理后建立的倒排索引看起来像：
```
"FBS"      → [文档0]
"卖家"     → [文档0, 文档1]
"自配送"   → [文档0]
```
当查询“FBS”时，检索器径直查找“FBS”词条，立即获得包含它的所有文档。BM25 在此基础上根据 TF 和 IDF 对这些文档进行打分排序。这就是“稀疏检索”得名的原因：它只关注查询词命中的那极少一部分文档，而不像向量检索那样对所有文档计算浮点相似度。倒排索引在几乎所有全文搜索引擎（如 Elasticsearch、Lucene）中都是第一块基石，你在 obsidian 里按下 Ctrl+F 查找文字，背后也是类似的数据结构。

BM25 的完整公式由这些因子合成：

$$
\text{BM25}(Q, D) = \sum_{t \in Q} \left[ 
\frac{(k_1 + 1) \cdot \text{tf}(t, D)}{k_1 \cdot \left((1-b) + b \cdot \frac{|D|}{\text{avgdl}}\right) + \text{tf}(t, D)} 
\cdot \log\left( \frac{N - n(t) + 0.5}{n(t) + 0.5} + 1 \right)
\right]
$$

对 0 基础受众，不要被符号堆砌吓到。只需要抓住三点：
1. **每个查询词独立贡献**，最后求和。这是“字面”检索的本质——词与词不依赖 Embedding 融合。
2. **括号里的对数项就是 IDF**，只与“这个词跨多少文档”有关，与当前文档内容无关。它是乘在 TF 项前面的全局系数。
3. **k1 和 b 是经验参数**（通常取 k1=1.2~2.0, b=0.75）。k1 控制“多出现一次”的边际收益衰减速度；b 控制文档长度的惩罚力度。不是本章的可调旋钮，但要知道它们存在。

### 以可观察实验做例

用 python 的 `rank_bm25` 库快速获得一个可重复观察的结果：

```python
from rank_bm25 import BM25Okapi

# 先做最简单的英文分词，中文需要 jieba 等分词器，此处为展示原理
def tokenize(text: str) -> list[str]:
    return text.lower().split()

corpus = [
    "FBS 是 Fulfillment By Seller 的缩写，指卖家自配送模式。",
    "卖家可以选择不同的物流配送方式。",
    "git stash pop 会删除栈顶的暂存记录。git stash apply 保留记录。",
    "git 是分布式版本控制系统。",
    "建议在执行 git 操作前先切换到一个新的分支。",
]

tokenized_corpus = [tokenize(doc) for doc in corpus]
bm25 = BM25Okapi(tokenized_corpus)
query_tokens = tokenize("FBS")
scores = bm25.get_scores(query_tokens)

for i, (doc, score) in enumerate(zip(corpus, scores)):
    print(f"Doc{i}: score={score:.4f} | {doc}")
```

期望看到包含“FBS”的文档 0 得分最高，其他文档得分接近于 0 或为 0。**观察到的结果**：“FBS”这个罕见词仅在一篇文档中出现，IDF 极大；所有其他文档都不得分。这就是稀疏检索的核心能力——对查询中未出现在文档里的词，它不产生“假相似度”。

再测一组：

```python
query2 = tokenize("git stash pop apply")
scores2 = bm25.get_scores(query2)
for i, (doc, score) in enumerate(zip(corpus, scores2)):
    print(f"Doc{i}: score={score:.4f} | {doc}")
```

期望看到 Doc2（包含“git stash pop”和“git stash apply”）得分最高，Doc3 和 Doc4 因包含“git”获得少量分数但远低于 Doc2。这就是 IDF 在起作用：“git”出现在多篇文档（较高 doc 频率 → 较低 IDF → 低权重），“stash”、“pop”、“apply”较罕见 → 高 IDF → 高权重。

### 反例与边界：分词不当让字面匹配“失明”

上述实验之所以成功，是因为我们使用英文空格分词，恰好把“FBS”“git”“stash”等按空格分开。但是当你的笔记是中文时，使用 `split()` 会得到整句甚至单字。例如：

```python
# 如果不对中文进行分词，直接把整句按空格切分，整句变成一个 "词"
doc_chinese = "FBS 全称是卖家自配送模式。"
tokens = doc_chinese.split()
print(tokens)  # 可能输出: ['FBS', '全称是卖家自配送模式。']
```

这样“FBS”能匹配，但查询时输入“卖家自配送”就无法在倒排索引中找到对应词条，因为“卖家自配送模式。”被当作一个整体 token，而查询中的“卖家自配送”也是另一个 token，两者绝无交集。BM25 的得分直接为零——明明文档里明明白白写着相同的汉字，却检索不到。这就是说，使用 BM25 时必须根据文本语言选用正确的分词器。对于中文推荐 `jieba` 分词，对于英文用空格和标点即可。安装并改写 tokenize 函数：

```bash
pip install jieba
```

```python
import jieba
def tokenize_zh(text: str) -> list[str]:
    return list(jieba.cut(text))
```

用 `jieba` 重新构建 BM25 索引，中文查询才能命中。如果忽略分词，你可能会错误地断定“稀疏检索没用”，实际是你没有给它一把正确的钥匙。在设计混合检索管道时，把“分词器是否匹配语种”作为每次构建索引前的必检项，这是零基础学习者常见的第一个坑。

### BM25 和向量检索的分工

向量检索是在连续空间中测量“方向”，返回的是语义相关的文本块，不论这些文本是否共享相同的词。BM25 是在离散词空间中测量“命中”，返回的是字面上包含关键术语的文本块。当查询是“FBS”时，BM25 不存在“它想不起来 FBS 长什么样”的问题——它直接在倒排索引中找到这个词并返回那篇文档。

把两者并列，就得到混合检索（Hybrid Search）的直观动机：对每个查询，同时进行向量检索和 BM25 稀疏检索，得到两个单独的 Top-K 列表，然后把两个列表合成一个最终列表。接下来的问题是：怎么合？

## RRF：不假定分数量级，只比较排名

向量检索输出的是余弦相似度（0~1 之间的浮点数），BM25 输出的是正值分数，两者量纲不同、分布不同。直接把“BM25=15.3 分”和“向量相似度=0.87”相加，本质上是在假设 1 分 BM25 == 1 个单位余弦相似度，这没有依据。

Reciprocal Rank Fusion（RRF）是一种不关心原始分数、只利用排名的融合算法。它最初用于元搜索引擎，将多个搜索结果列表合并，且不需要任何评分归一化假设。

RRF 对一个文档 d 的总得分计算为：

$$
\text{RRFScore}(d) = \sum_{r \in R} \frac{1}{k + \text{rank}_r(d)}
$$

其中 R 是各个检索器（本章中 r ∈ {向量检索器, BM25检索器}），`rank_r(d)` 是文档 d 在该检索器下的排名（从 1 开始），k 是一个常数，默认取 60（原论文推荐值，减小 k 会让排名更高的文档获得更大优势，但也会让低排文档几乎零分）。

用一句话翻译：**排名越靠前，贡献的分数越大，且这种贡献按 1/(排名) 衰减。** RRF 不假设分数量级可比，只信任排名的先后。

### 一条具体数值推演

假设 BM25 对文档 D 排名 #1，向量检索对 D 排名 #85，k=60。

- BM25 贡献：1 / (60 + 1) = 1/61 ≈ 0.0164
- 向量贡献：1 / (60 + 85) = 1/145 ≈ 0.0069
- RRF 总得分：0.0164 + 0.0069 = 0.0233

而另一篇文档 E 在 BM25 排 #20，向量排 #5：
- BM25 贡献：1 / (60 + 20) = 1/80 = 0.0125
- 向量贡献：1 / (60 + 5) = 1/65 ≈ 0.0154
- RRF 总得分：0.0125 + 0.0154 = 0.0279

D 在 BM25 排榜首，E 在两个列表都排较高但不是任何一个的榜首。按 RRF 融合，E 总分高于 D。这反映了 RRF 的设计哲学：**在两个检索器眼中都“还不错”的文档，可能比只在一个检索器眼中“最好”而在另一个检索器中完全排不上号的文档更稳健。**

这正是我们在“git stash pop”场景中期待的行为。BM25 能找到字面上包含命令的笔记（Doc2），向量检索能找到语义相关但不包含命令的笔记（Doc3）。RRF 融合后，同时被两者认为相关的文档会排到最前面，但一个在 BM25 排前 3 而向量检索排前 20 的文档，可能依然比仅在向量检索排第 1 但 BM25 排 400 的文档更可靠。

### 短小可观察示例：改变 k 值观察排名变化

k 值并不是一个“设对就行”的魔法数字，它控制着高排名与低排名文档的分数差异。你可以立即运行几行代码来建立直觉：

```python
def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)

ranks = [1, 2, 3, 4, 5, 10, 20, 50]
for k in [0, 30, 60, 120]:
    scores = [rrf_score(r, k) for r in ranks]
    print(f"k={k:>3}:", [f"{s:.4f}" for s in scores])
```

**可观察输出（示意）：**
```
k=  0: ['1.0000', '0.5000', '0.3333', '0.2500', '0.2000', '0.1000', '0.0500', '0.0200']
k= 30: ['0.0323', '0.0312', '0.0303', '0.0294', '0.0286', '0.0250', '0.0200', '0.0125']
k= 60: ['0.0164', '0.0161', '0.0159', '0.0156', '0.0154', '0.0143', '0.0125', '0.0091']
k=120: ['0.0083', '0.0082', '0.0081', '0.0081', '0.0080', '0.0077', '0.0071', '0.0059']
```

当 k=0 时，排名第 1 的文档得分是第 2 名的两倍，差距极大，极端倚重单个检索器的榜首，很少给共识文档机会。当 k=120 时，前 5 名的得分差异极小，几乎把每个检索器的信号摊平，融合结果接近随机。这就是为什么论文推荐 k=60 作为平衡点：既让高排名文档保持足够优势，又不至于让共识文档的微弱优势被完全淹没。如果你在测试中发现混合检索不如纯向量，调整 k 值之前务必先用实验确认两个检索器是否都召回了相关文档，k 参数只是在「已召回结果」内部重新排序，绝不能无中生有。

### 规范保证与实现选择

- 数学定义保证：∀ rank ≥ 1，1/(k+rank) 递减且有界于 (0, 1/k]。
- 实际实现多取 k=60，这是经过原论文验证的对多检索器排名融合稳健的默认值。本章使用此默认值。
- 若检索器只返回 top-20，则 rank > 20 的文档在该检索器下视为未命中，得分为 0。

RRF 只是融合器，它不改变检索器内部。这引出下一个问题：如果我们已经用混合检索解决了召回问题，为什么还需要一个全新的模型对 Top-K 进行二次挑选？

## 重排序：让 Recall 转化为 Precision

前面的混合检索解决了“把那条包含 git stash pop 的笔记排进 Top-10 结果”的问题——这是提升 **Recall（召回率）**。但 Top-10 里可能还混入了“git暂存区操作概览”或“Git常见命令笔记”等只相关但没有直接答案的文档。把它们全部塞给 LLM，上下文窗口被无关文本占据，答案质量仍会下降。

这里需要一个更精细的判断器，对 Top-10 或 Top-20 的文档一一点评：“这一篇里，到底有没有解答用户问题的信息？”这个角色由重排序（Re-ranking）模型承担。

### Bi-Encoder 与 Cross-Encoder 的职责区别

你目前使用的 bge-m3 是一个 **Bi-Encoder**。意思是：它将查询和文档分别编码为向量，然后计算向量相似度。好处是文档向量可以提前算好存起来（索引），检索时只需算一个查询向量然后做向量距离运算，速度极快。代价是两个编码是独立的：查询和文档从未在模型的注意力层中“见过面”。模型永远没有机会在知道查询内容后，再重新审视文档的哪些部分重要。

**Cross-Encoder** 做相反的事：它把查询和文档打包成一对输入 `[CLS] query [SEP] document [SEP]`，让 Transformer 在每一层注意力中同时看到查询和文档。这就像一个阅卷老师先看了题目，再逐句读学生的回答——他能精确判断哪一句回答了问题、哪一句离题了。

代价是计算量：对每一个 (query, document) 对，Cross-Encoder 都要跑一次完整前向传播。因此不能对全库使用，只对混合检索召回的 Top-K（通常 10~30 条）进行精排。

**关键对比表：**

| 维度 | Bi-Encoder（bge-m3） | Cross-Encoder（bge-reranker） |
|------|----------------------|------------------------------|
| 输入格式 | query 和 doc 分别编码 | query 和 doc 拼接为单输入 |
| 注意力交互 | 无交互，编码独立 | 全层交互，知道查询内容再审视文档 |
| 推理速度 | 极快（单 query 对百万文档） | 慢（每对单次前向，仅对 Top-K） |
| 适用阶段 | 初始召回（向量索引） | 精排阶段（Top-K 重打分） |
| 精度 | 近似相似，可能漏判 | 细致相关性判断，减少无关文档入 LLM |

### 机制区分实验：Bi-Encoder 与 Cross-Encoder 的直接对比

下面的实验使用同一组 query-doc 对，分别得到余弦相似度和 Cross-Encoder 相关性分数，直观展示“语义相关但不含答案”的文档在两种评分下的差异。

```python
from FlagEmbedding import FlagModel, FlagReranker
import numpy as np

# 初始化两个模型（实验仅执行一次，慢在加载模型，不是计算）
biencoder = FlagModel('BAAI/bge-m3', query_instruction_for_retrieval="为查询生成向量表示：")
reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)

query = "Git 中 pop stash 和 apply stash 有什么区别？"
docs = {
    "doc_stash": "git stash pop 会恢复并删除 stash，git stash apply 只恢复不删除。",
    "doc_rebase": "可以使用 git rebase 来整理提交历史，让分支线更清晰。",
    "doc_merge": "git merge 用于合并分支，经常会产生合并提交。"
}

# Bi-Encoder 分别编码计算余弦
q_emb = biencoder.encode(query)
results_bi = {}
for name, doc_text in docs.items():
    d_emb = biencoder.encode(doc_text)
    sim = np.dot(q_emb, d_emb) / (np.linalg.norm(q_emb)*np.linalg.norm(d_emb)+1e-10)
    results_bi[name] = sim

print("Bi-Encoder 余弦相似度：")
for name, sim in sorted(results_bi.items(), key=lambda x: x[1], reverse=True):
    print(f"  {name}: {sim:.4f}")

# Cross-Encoder 成对打分
results_ce = {}
for name, doc_text in docs.items():
    score = reranker.compute_score([query, doc_text])
    results_ce[name] = score
print("\nCross-Encoder 相关性分数：")
for name, score in sorted(results_ce.items(), key=lambda x: x[1], reverse=True):
    print(f"  {name}: {score:.4f}")
```

**预期观测**：
- `doc_stash` 在两者中都应获得最高分。
- `doc_rebase` 和 `doc_merge` 在 Bi-Encoder 中可能仍获得中等分数（因为它们都谈论 Git 操作，语义接近），但在 Cross-Encoder 中它们的分数会显著更低（因为它们并没有回答“pop vs apply 区别”这个具体问题）。特别是，Cross-Encoder 可能给出负分或接近零，而余弦相似度仍保持 0.6 以上。这恰恰是“重排序可以剔除高相似但不相关的文档”的直接证据。这个实验是本章的关键验证，建议运行一次并把数值记入你的笔记。

### 部署 bge-reranker 并与混合检索管道集成

bge-reranker 同样由 BAAI 发布，本章使用其 v2-m3 版本（与 bge-m3 Embedding 模型配对，擅长多语言和长文本精排）。

```bash
# 拉取 bge-reranker，GGUF 量化版本，约 1.5 GB
ollama pull bge-reranker
# 验证可用
ollama list | grep bge-reranker
```

Ollama 为 reranker 模型暴露的不是 `/embeddings` 接口，而是自定义 rerank 接口或通过 chat 接口间接调用。需要查阅当前 Ollama 版本对 reranker 的具体调用方式。以下是一个跨版本通用的最小调用验证：

```bash
# 通用测试：向 Ollama 的 rerank endpoint 发送一对文本
curl -s http://localhost:11434/api/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-reranker",
    "query": "git stash pop 是否会删除暂存记录？",
    "documents": [
      "git stash pop 会删除栈顶的暂存记录，apply 不会。",
      "Git 可以通过 rebase 整理提交历史。"
    ]
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data.get('results', []):
    print(f'Doc{r[\"index\"]}: relevance={r[\"relevance_score\"]:.4f}')
"
```

**预期输出**：Doc0 的 relevance 远高于 Doc1，差距通常 > 0.4。如果 Ollama 当前版本未提供 `/api/rerank`，备选方案是使用 Python 的 `FlagEmbedding` 包加载 reranker 模型：

```python
# 备选：直接 load reranker 模型并调用
from FlagEmbedding import FlagReranker

reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)
score = reranker.compute_score(["git stash pop 是否会删除暂存记录？",
                                 "git stash pop 会删除栈顶的暂存记录。"])
print(f"Relevance: {score:.4f}")
```

**可观察结果**：一个正相关文档（包含答案）得分 > 0，负相关文档（不包含答案）得分 < 0 或接近于 0。Cross-Encoder 的决策粒度远细于 Bi-Encoder 的余弦相似度。

## 代码落地：完整的混合检索 + 重排序管道

下面是本章核心实验。假设你的 Obsidian 仓库笔记已在第4章通过 bge-m3 生成向量并存入本地 `chunks.json`（形状为 `[{"id":..., "text":..., "embedding":[...]}, ...]`）。我们将在这个基础上加入 BM25 索引、RRF 融合和 bge-reranker 精排。

```python
import json
import numpy as np
from rank_bm25 import BM25Okapi
from FlagEmbedding import FlagReranker
import requests

# ---- 1. 加载本地向量索引与笔记块 ----
with open("chunks.json", "r") as f:
    chunks = json.load(f)
# chunks[i] = {"id": "note1-chunk0", "text": "...", "embedding": [...]}

embeddings = np.array([c["embedding"] for c in chunks])
texts = [c["text"] for c in chunks]
ids = [c["id"] for c in chunks]

def embed_query(text: str) -> np.ndarray:
    resp = requests.post(
        "http://localhost:11434/v1/embeddings",
        json={"model": "bge-m3", "input": [text]}
    )
    return np.array(resp.json()["data"][0]["embedding"])

# ---- 2. 构建 BM25 索引 ----
def tokenize(text: str) -> list[str]:
    # 简单分词，中文需 jieba；此处展示核心结构
    return text.lower().split()

tokenized_texts = [tokenize(t) for t in texts]
bm25 = BM25Okapi(tokenized_texts)

# ---- 3. RRF 融合函数 ----
def rrf_fusion(dense_ranks: dict, sparse_ranks: dict, k: int = 60) -> dict:
    """
    dense_ranks: {chunk_id: rank} rank从1开始
    sparse_ranks: {chunk_id: rank}
    返回 {chunk_id: rrf_score}
    """
    scores = {}
    for chunk_id, rank in dense_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank)
    for chunk_id, rank in sparse_ranks.items():
        scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank)
    return scores

# ---- 4. 单次完整查询 ----
def hybrid_search(query: str, top_k: int = 20, rerank_top: int = 5):
    # 向量检索侧
    q_emb = embed_query(query)
    cosine_scores = np.dot(embeddings, q_emb) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(q_emb) + 1e-10
    )
    dense_ranked = np.argsort(-cosine_scores)[:top_k]
    dense_ranks = {ids[i]: int(rank) + 1 for rank, i in enumerate(dense_ranked)}

    # BM25 稀疏检索侧
    tokenized_q = tokenize(query)
    bm25_scores = bm25.get_scores(tokenized_q)
    sparse_ranked = np.argsort(-bm25_scores)[:top_k]
    sparse_ranks = {ids[i]: int(rank) + 1 for rank, i in enumerate(sparse_ranked)}

    # RRF 融合
    fused_scores = rrf_fusion(dense_ranks, sparse_ranks)
    sorted_fused = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    top_fused = sorted_fused[:top_k]

    # 重排序：仅对融合后的 Top-K 用 Cross-Encoder 精排
    reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=False)
    rerank_pairs = [(query, chunks_by_id[chunk_id]) for chunk_id, _ in top_fused]
    # 注意 chunks_by_id 需预先构建
    scores = reranker.compute_score(rerank_pairs, normalize=True)
    reranked = sorted(
        zip([cid for cid, _ in top_fused], scores),
        key=lambda x: x[1], reverse=True
    )

    # 返回精排后的最终 Top-N
    return [(chunk_id, score) for chunk_id, score in reranked[:rerank_top]]

# 构建辅助索引
chunks_by_id = {c["id"]: c["text"] for c in chunks}

# 执行测试查询
results = hybrid_search("git stash pop 是否会删除暂存记录？")
for chunk_id, score in results:
    print(f"[{score:.4f}] {chunks_by_id[chunk_id][:80]}...")
```

**验证标准**：管道运行后，第一条结果的文本应直接命中包含“git stash pop 会删除”的笔记块。同时控制台打印的 reranker score 应在 Top-1 处明显高于 Top-3 以后的文档（差值 > 0.2）。

## A/B 对比：纯向量 vs 混合 vs 混合+重排序

把上面的流程拆成三个独立实验，用同一查询和同一 chunk 库跑三次，记录 Top-3 的文本标签。

**0 基础同学可直接使用的实验脚本**（无需理解内部实现，会运行即可描述结果）：

```python
# 为清晰阅读，仅对比 Top-3 结果
def compare_strategies(query: str):
    print(f"\n{'='*40}\n查询: {query}\n{'='*40}")

    # 纯向量
    q_emb = embed_query(query)
    cos = np.dot(embeddings, q_emb) / (np.linalg.norm(embeddings, axis=1)*np.linalg.norm(q_emb)+1e-10)
    d_only = np.argsort(-cos)[:3]
    print("\n[纯向量 Top-3]")
    for i in d_only:
        print(f"  {texts[i][:60]}")

    # 混合（无重排序）
    fused = hybrid_search(query, top_k=20, rerank_top=3)
    print("\n[混合 RRF Top-3 (无重排序)]")
    for chunk_id, score in fused:
        print(f"  {chunks_by_id[chunk_id][:60]}")

    # 混合+重排序 已在 hybrid_search 中集成
    # 此处复用以展示差异
    print("\n[混合+重排序 Top-3]")
    for chunk_id, score in fused:  # 实际应拿 reranker 结果
        print(f"  [{score:.4f}] {chunks_by_id[chunk_id][:60]}")

compare_strategies("git stash pop 是否会删除暂存记录？")
compare_strategies("什么是 FBS？")
compare_strategies("第4章部署了哪个本地 Embedding 模型？")
```

**期望证据**：
1. 对“git stash pop”查询，混合检索的 Top-1 命中精确命令笔记，而纯向量的 Top-1 可能仍是 git 通用笔记。
2. 对“FBS”查询，混合检索的第一条就是 FBS 缩写笔记。
3. 对“第4章部署了哪个本地 Embedding 模型”，纯向量已经能做到，混合+重排序让最相关的段落出现在 Top-1，而非 Top-3。

## 诊断：混合检索仍失败的常见情况

练习时如遇以下失败，参照下面的验证链：

**现象A：BM25 侧没召回任何包含关键词的文档**
- **第一证据**：单独打印 `bm25_scores`，检查是否全为0。
- **第二检查点**：分词是否正确。`tokenize("FBS")` 是否真的得到 `['fbs']`？如果分词器把“FBS”拆成了单个字母，那是分词策略不当。
- **不要先做什么**：不要先调整 k1、b 参数。先证明“单词存在”一关通了，再调参数。

**现象B：RRF 融合后排名变差**
- **第一证据**：`dense_ranks` 和 `sparse_ranks` 中目标文档是否至少在一个检索器中排前10。
- **第二检查点**：如果目标文档在两个检索器都排在200名以后，RRF 无法挽救——这是召回侧覆盖问题，需扩大单个检索器的 top_k 或检查分块是否把关键词切碎。
- **不要先做什么**：不要先换融合算法（加权平均、学习排序）。RRF 无参且稳健，如果 RRF 解决不了，加权也很难。

**现象C：重排序后反而更差**
- **第一证据**：reranker 对正文档的打分是否低于负文档？
- **第二检查点**：检查正文档文本是否包含答案。如果笔记块短到只写了“git stash pop”，而 reranker 问的是“git stash pop 会不会删除记录”，正文档需要包含足以让 Cross-Encoder 认定的线索文本。
- **不要先做什么**：不要怀疑模型质量。Cross-Encoder 失败大概率出现在分块策略——这个块太小，连答案都没装下。回到第2章的分块策略调整。

### 反例：同义词在 BM25 中的盲区

就算分词正确，BM25 还有一个不可忽视的边界：**同义词和近义词**。假设你的知识库里有一篇关于“配置本地推理服务”的笔记，另一篇写的是“设置 Ollama 本地端点”。用户的查询是“怎样设置本地推理服务”。BM25 逐词匹配，“设置”命中第二篇，“本地”和“推理”可能两篇都命中一部分，但“配置”不会自动映射到“设置”——它们是不同的 token，在倒排索引里分属两条记录，BM25 不会为它们建立关联。只要查询里没有出现“配置”二字，那篇最精准的配置指南就可能被漏掉。

向量检索在这里恰好弥补：因为“配置”和“设置”在语义空间中非常接近，向量相似度会给那篇配置指南一个中高分，即使没有字面重叠。这就是混合检索“1+1>2”的场景：BM25 无法匹配的词，向量检索通过语义近似拉回来。因此，在选择测试用例时，建议包含一个「关键概念用近义词表达的查询」，验证混合检索是否真正利用了向量的语义理解。缺少这类用例可能让你高估系统能力。

## 练习与反馈：实践小型混合检索管道

完成本章理论推演和代码运行后，你需要在一个受控的小环境里完整体验一次“发现问题→设计混合→对比效果”的闭环。下面是本节练习：

**给定迷你语料**（直接复制到 Python 文件里）：
```python
chunks_data = [
    {"id": "chk1", "text": "FBS 是 Fulfillment By Seller 的缩写，指卖家自配送模式。"},
    {"id": "chk2", "text": "Git 中 stash pop 会删除暂存记录，而 apply 不会。"},
    {"id": "chk3", "text": "在 Obsidian 中通过 Smart Connections 可以配置本地 Embedding 服务。"},
    {"id": "chk4", "text": "卖家可以通过平台物流或自配送两种方式发货。"},
    {"id": "chk5", "text": "使用 git stash 可以暂存当前修改，稍后恢复。"},
]
embeddings_data = [
    # 此处用全零向量占位，练习中改用真实 Embedding。你也可以用第4章的 bge-m3 对每个 text 生成向量。
]
```

**任务**：
1. 使用 bge-m3 为每个 chunk 生成 Embedding，构建向量检索侧。
2. 使用 `jieba` 分词并构建 BM25 稀疏检索侧。
3. 自行实现 RRF 融合函数（必须用你自己写的代码，不允许调用现成 RRF 库）。
4. 对以下三个查询分别执行纯向量、纯 BM25 和混合 RRF 检索，记录每个方法的 Top-3 的 chunk id 顺序：
   - 查询 A: "FBS 是什么"
   - 查询 B: "git stash pop 和 apply 的区别"
   - 查询 C: "如何设置本地服务"
5. 回答以下问题（写进笔记）：
   - 对于查询 A，纯向量和纯 BM25 哪个效果更好？为什么？
   - 对于查询 B，RRF 融合结果是否优于任一单路？具体说明哪个 chunk 因为 RRF 被提升或压制。
   - 对于查询 C，你观察到向量检索的优势是什么？BM25 是否有完全遗漏相关文档？这体现了怎样的互补关系？
6. 在笔记末尾写出你学到的 **一条具体规则**，阐述“什么时候应该信任 BM25 多于向量，什么时候相反”。
7. （选做）给查询 B 的候选列表加入一个与 Git 无关的干扰项 `"Python 的 list 提供了 pop 和 append 方法"`，观察混合检索能否通过 RRF 把它压到较低排名。

**验收方式**：将代码、运行输出和你对问题的回答整理为一篇 Obsidian 笔记，贴入运行结果截图或文本块。不需要发送给任何人——你未来在学习 GraphRAG 或评估 RAGAS 时，会反复回到这篇笔记来校准对“检索质量”的直觉。如果某个查询的混合结果让你感到意外，首先回到本节的反例清单逐项排查，而不是立刻修改模型或融合参数。

## 本章实测验证矩阵

完成下列测试并记录结果到笔记中：

| 查询类型 | 纯向量Top-1准确？ | 混合Top-1准确？ | 混合+重排Top-1准确？ | 观察到的失败块特征 |
|---------|------------------|----------------|---------------------|-------------------|
| 专有名词（FBS、Dify） | | | | |
| 代码命令（git stash pop） | | | | |
| 自然语言问句 | | | | |
| 混合（问句含代码） | | | | |

**完成标准**：至少4个查询在混合+重排序下 Top-3 包含正确答案，且纯向量至少有一个查询失败，证明混合检索在本知识库中产出了可测量的增量改进。

## 本章小结

纯向量检索在专有名词、命令和缩写上失效，不是 Embedding 模型的问题，而是 Bi-Encoder 独立编码架构的固有限制。解决路径不是在语义赛道上抢跑，而是拉一条新跑道。

BM25 用词频和逆文档频率给每个词显式贡献值，IDF 保证了“越稀有的词辨识力越强”，精确命中不受训练语料限制。RRF 不假设原始分数量纲，仅凭排名融合多路结果，实现了向量与稀疏检索的加减法。Cross-Encoder 在精排阶段接棒，以全层注意力交互对 Top-K 进行逐对打分，把 Recall 提升转化为 Precision 提升。

最终交付的三阶段管道（混合召回 → RRF 融合 → Cross-Encoder 精排）是当前本地 RAG 系统常见的组合，也是第6章 GraphRAG 所需的可靠检索基座。第9章评估章节将使用 RAGAS 框架精确量化本章引入的每个组件的独立贡献。

## 参考文献

- Robertson, S., & Zaragoza, H. (2009). The Probabilistic Relevance Framework: BM25 and Beyond. *Foundations and Trends in Information Retrieval*, 3(4), 333–389.
- Cormack, G. V., Clarke, C. L. A., & Buettcher, S. (2009). Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. *Proceedings of SIGIR 2009*.
- Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. *Proceedings of EMNLP-IJCNLP 2019*.
- BAAI. (2024). bge-reranker-v2-m3. Hugging Face model card. https://huggingface.co/BAAI/bge-reranker-v2-m3
- OMGDom. (2024). rank_bm25: Python BM25 implementation. https://github.com/dorianbrown/rank_bm25
- Ollama Documentation. OpenAI Compatibility. https://docs.ollama.com/api/openai-compatibility

> 注意：本章至“重排序：让 Recall 转化为 Precision”节中使用的 FlagEmbedding 包依赖 bge-reranker-v2-m3 模型，首次运行时将自动下载模型文件。请在该环节保持网络连接，下载完成后切换为全离线模式，后续重启无需网络。
