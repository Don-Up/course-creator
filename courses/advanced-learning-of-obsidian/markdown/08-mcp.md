# 第 8 章 开发者扩展——基于 MCP 与外部生态联动

> 预计学习时间：180–260 分钟
> 一句话总结：用 MCP 协议把 Obsidian 知识库变成你所有开发工具的「上下文提供者」，再用 Python 脚本让笔记变动自动流向外部向量数据库——让笔记成为跨工具可调用的数据源。

## 为什么你的知识库无法与工具对话？——理解本章要解决的问题

你已经完成了前 7 章的全部工作：笔记里沉淀了 RAG 原理、Ollama 配置、混合检索调参经验、GraphRAG 实体解析的踩坑记录，甚至还有 3D 图谱里发现的“星桥笔记”。这些知识在你打开 Obsidian 时触手可及，但当你切换到 Cursor 写代码、用 Claude Code 分析项目、或者维护第 4 章搭建的本地 RAG 系统时，它们统统“消失”了——你得手工搜索、复制、粘贴，来回切换窗口。每次切换都在消耗你的注意力，每条已经思考过的结论都可能因为“懒得去翻”而从未被真正复用。

问题的根源不在于你有两个程序，而在于：**你的知识库是一个被动的仓库，不是一个能响应外部请求的服务**。IDE 不能“问”你的笔记“我们上次 BM25 的 k 值调试结论是什么”，外部向量数据库不能“订阅”你刚刚写好的新笔记——知识库就像一间没有门的图书室，书都在里面，但你得亲自走进去翻。

本章只负责解决这一个问题，使用的工具是 **MCP（Model Context Protocol，模型上下文协议）**。当前章节覆盖的能力包括：理解 MCP 的 Client-Server 模型与三类抽象（Resources、Tools、Prompts）；用 Python 构建一个暴露笔记查询和图搜索的 MCP Server；在 Cursor 或 Claude Code 中完成 IDE 级知识库集成验证；以及用 Python 脚本监听 Markdown 变动并将变化自动写入外部向量数据库。**本章不展开**的内容包括 Agentic 自动写回能力（留给第 9 章）、MCP 的 HTTP 传输模式与多客户端并发、生产级权限控制与加密。前置条件：已具备 Obsidian 深度使用经验（前 7 章）、理解本地 API 的基本概念（第 4 章）、命令行操作能力。本章使用的固定版本是 Python ≥ 3.10、MCP Python SDK 最新稳定版（通过 pip 安装）、LanceDB 嵌入式向量库。

## 从杂乱到统一——MCP 如何让工具“说同一种语言”

### 一个 N×M 的集成噩梦

在引入 MCP 之前，让外部工具访问 Obsidian 知识库的常见做法是“一对一适配”：

- 你在 Cursor 里想让 AI 引用笔记 → 需要写一个 Cursor 扩展，遍历目录、解析 Markdown、提取 frontmatter 和双链。
- 你用 Claude Code 做代码审查时也想引用笔记 → 又需要一个 Claude Code 适配器，把搜索结果拼进提示词。
- 你甚至可能还想让 Windsurf 也具备同样能力 → 第三个实现。

这三个适配器有至少 80% 的逻辑完全相同（文件遍历、解析、双链提取），但因为你必须在各自插件的语言和 API 下重新实现三次，加上后续 vault 结构或 Obsidian 格式升级时三者都要同步修改——这就是 **N×M 问题**：工具数量与知识库类型的乘积。M 个工具、N 种知识库，就需要 M×N 套适配代码。对于同时使用两个 IDE 和你自己一套 vault 的情形，这已经有至少两套适配器要维护。

MCP 解决的核心问题正是这个：它定义了一套统一的 Client-Server 通信规范。你只需实现**一个** MCP Server，把你的笔记能力——搜索、读取、元数据过滤——按照协议暴露出来；所有支持 MCP 的 Client（Cursor、Claude Code、Windsurf 等）都能通过同一套协议与你的知识库交互。N×M 变为 N+M。

MCP 由 Anthropic 提出并开源，协议规范公开可查。本章引用的协议版本为 2025-06-18 版规范（见本章参考文献）。

### 最小前置：stdin、stdout 与子进程

本章后续会大量涉及“通过 stdin/stdout 通信”。如果你过去只编写过带有图形界面的程序，这里先建立几个最基本的认识：

- **stdin（标准输入）**：程序读取用户输入的地方。当你在终端里敲键盘，你敲的内容进入了程序的 stdin。在 Python 中，`input()` 从 stdin 读取。
- **stdout（标准输出）**：程序输出结果的地方。`print()` 把内容写入 stdout，所以你能在终端看到。
- **子进程**：一个程序可以启动另一个程序——被启动的就是子进程。父进程能向子进程的 stdin 写入数据，子进程的 stdout 能被父进程读取。

你可以打开终端，亲自试验：

```bash
# 创建文件 test_io.py，内容只有一行: print("hello stdout")
echo 'print("hello stdout")' > test_io.py

# 用 Python 启动子进程，并捕获子进程的 stdout
python3 -c "
import subprocess
result = subprocess.run(['python3', 'test_io.py'], capture_output=True, text=True)
print('捕获到的输出:', result.stdout)
"
# 输出: 捕获到的输出: hello stdout
```

你对这个过程的理解不需要深入到系统调用级别，只需要记住一个类比：**父进程启动子进程，就像一个人用对讲机指挥另一位同事——所有指令通过对讲机发送，对方完成后通过对讲机回报结果，全程不在公开频道上**。这就是 MCP 使用 stdio 时的交互模型。

### 进程间安全通信——为什么 MCP 使用 stdio

在进入概念细节之前，你需要先理解本章 MCP Server 的通信基础：**标准输入输出（stdin/stdout）**。MCP Server 不监听网络端口——客户端（如 Cursor）把 `python3 server.py` 当作一个子进程启动：

1. Cursor 将 JSON-RPC 请求写入这个子进程的 **stdin**（相当于你通过键盘向程序输入数据）。
2. Server 处理请求后，把 JSON-RPC 响应写入自己的 **stdout**（相当于程序在终端打印结果）。
3. Cursor 读取子进程的 stdout 获得响应。

这意味着：**没有网络配置、没有防火墙规则、没有端口冲突**。数据只在你的本机两个进程之间流转，永远不触及网络。相比之下，如果使用本地 HTTP 服务器（如 `http://localhost:8080`），你需要配置端口、处理跨域、还要防止同网段其他设备的未授权访问——攻击面大得多。**一个常见的反例**：假设你图省事把 MCP Server 改成了监听 `localhost:8080` 的 HTTP 服务。任何运行在你机器上的其他程序——包括带有恶意脚本的浏览器插件——都可以向 `http://localhost:8080` 发送请求，读取你的笔记全文。而 stdio 天然地把通信限制在父进程与子进程之间，第三方进程无法注入请求，这就是后续安全部分要强调的隐私优势。

### Resources、Tools、Prompts——MCP 的三类抽象

MCP Server 可以暴露三类能力，它们各自对应一种交互模式：

| 概念 | 做什么 | 交互方向 | 在 Obsidian MCP Server 中的体现 |
| --- | --- | --- | --- |
| **Resources** | 暴露可读取的数据 | Client 主动拉取 | 笔记列表、笔记正文、图谱邻接信息 |
| **Tools** | 暴露可执行的操作 | Client 请求执行，Server 返回结果 | 全文搜索笔记、按标签过滤、查询反向链接 |
| **Prompts** | 暴露预置的提示词模板 | Client 拉取模板并参数化 | “总结今日笔记”“寻找与本笔记相关但未链接的内容” |

本章的 MCP Server 实现重点放在 **Resources** 和部分 **Tools** 上，优先让外部工具能够“读到”知识库的内容。完整的 CRUD（创建、更新、删除笔记）属于第 9 章 Agentic 闭环的范畴——因为只有那时我们才真正需要“自动写回笔记”。Prompts 不在本章手动编写，但客户端后续可以将 Resources 返回的内容动态填充到自己的提示模板中，达到类似效果。

**MCP 与文件系统 API 的本质区别**：你可能会问：Cursor 不是本来就能读本地文件吗？通过文件 API 打开 `~/Documents/Obsidian/Vault/某笔记.md` 不就行了？区别在于**语义理解层级**。

用一个例子说明区别：假设你的 vault 中有一篇名为“混合检索实验”的笔记，它内有 frontmatter `tags: [rag, search]`，并包含正文：“试验在 50 篇笔记上用 BM25 + 向量，RRF 融合后 MAP 从 0.31 提升到 0.47，但 BM25 介入过强导致专有名词召回反而下降。”

- **文件系统 API 看到的是**：`文件路径: 混合检索实验.md`，`字节数: 1534`，`内容: "---\ntags: [rag...\n---\n试验在50篇笔记上..."`。它能搜索字符串“0.31”，但无法理解 `tags` 是元数据、无法知道“BM25”出现在一个“实验”上下文中、更无法告诉你“还有哪篇笔记提到了 RRF”。
- **MCP Server 看到的是**：`title: 混合检索实验`，`tags: [rag, search]`，`双链: [[BM25调参记录]]`。当 LLM 需要引用你的实验结论时，Server 返回的是结构化信息而非原始字节流，这使得 AI 助手的回答更准确且带引用来源。

以一次交互为例：你在 Cursor 中要求“总结我所有关于 RAG 的笔记”，Cursor 首先调用 `search_notes` Tool 获得匹配文件列表，然后对每个文件调用 `read_resource` 获取完整内容（含 frontmatter 元数据和双链），最后将这一批结构化笔记注入 LLM 的上下文窗口。如果没有 Tool 这一层抽象，Cursor 只能通过文件系统 API 去“猜”哪些文件与 RAG 相关——它可能会列出所有文件名中包含“RAG”的 .md 文件，却遗漏了你那篇标题为“混合检索实验”但 tags 中包含 `rag` 的关键笔记。Tool 允许 Server 端利用自己对 vault 结构的理解来执行语义更丰富的匹配，而不是把原始文件列表一股脑丢给客户端自行解析。

### 一次查询的内部旅程——MCP 请求的生命周期

从你在 Cursor 里问“我的笔记里关于 BM25 调参的结论是什么”，到 AI 助手给出引用笔记的回答，MCP 协议内部经历了以下步骤：

```text
Cursor (MCP Client)                    Obsidian MCP Server
         │                                       │
         │  1. 建立连接（stdio）                   │
         │──────────────────────────────────────→│
         │                                       │
         │  2. initialize 握手                    │
         │     客户端声明协议版本与能力              │
         │←──────────────────────────────────────│
         │     服务端返回自身能力（Resources/Tools） │
         │                                       │
         │  3. resources/list 获取资源列表          │
         │──────────────────────────────────────→│
         │←──────────────────────────────────────│
         │     [笔记 URI、搜索工具定义…]            │
         │                                       │
         │  4. tools/call 调用搜索工具              │
         │     参数: {"query": "BM25 调参 k值"}    │
         │──────────────────────────────────────→│
         │                                       │
         │  5. Server 在本地文件系统搜索            │
         │     遍历 vault → 全文匹配              │
         │                                       │
         │  6. 返回匹配文件的 URI 与上下文片段       │
         │←──────────────────────────────────────│
         │                                       │
         │  7. resources/read 读取完整笔记内容       │
         │──────────────────────────────────────→│
         │←──────────────────────────────────────│
         │     Markdown 正文（含 frontmatter）     │
         │                                       │
         │  8. Cursor 将笔记内容注入 LLM 上下文     │
         │     LLM 基于你的笔记而不是通用知识回答    │
```

关键节点：第 2 步的 `initialize` 握手允许服务端主动声明能力——就像插上 U 盘后操作系统自动识别它是存储设备，不需要你手动指定驱动类型。第 5-6 步的搜索完全在本地文件系统上完成，不经网络，不依赖外部搜索引擎。第 8 步才是 LLM 开始工作的时刻——MCP Server 本身不调用任何大模型，它只是数据检索层。这很关键：Server 与 LLM 的职责分离意味着你可以独立升级 AI 模型（例如从 GPT-4 换成本地模型），而知识库的暴露方式和搜索逻辑完全不受影响，无需改动一行 Server 代码。

### 在集成 IDE 之前——用最小客户端脚本先验证

在正式配置 Cursor 或 Claude Code 之前，你可以用一段简短的 Python 脚本直接验证 MCP 通信链路是否畅通。这比盲目跳进 IDE 配置更可控，出错也更容易定位。

**首先要做一次快速验证**：在你的 `server.py` 所在目录直接执行 `python3 server.py`。Server 启动后会等待 stdin 输入，不会打印任何提示——这是正常行为，不是卡死。按 `Ctrl+C` 退出。如果此步失败，检查是否进入了虚拟环境、依赖是否全部安装。

现在编写 `~/obsidian-mcp-server/test_client.py`：

```python
#!/usr/bin/env python3
"""最小 MCP 客户端：连接 obsidian-mcp-server 并列出所有笔记"""
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

async def main():
    # 启动 server.py 作为子进程，通过 stdio 建立连接
    async with stdio_client("python3 server.py") as (read, write):
        async with ClientSession(read, write) as session:
            # 初始化握手
            await session.initialize()
            # 列出 Resources
            resources = await session.list_resources()
            print(f"发现 {len(resources.resources)} 个笔记资源")
            for res in resources.resources[:10]:  # 只显示前 10 个
                print(f"  - {res.name}: {res.uri}")

if __name__ == "__main__":
    asyncio.run(main())
```

运行（确保已在虚拟环境中）：

```bash
cd ~/obsidian-mcp-server
source venv/bin/activate
python3 test_client.py
```

应该看到类似输出：

```
发现 42 个笔记资源
  - RAG 原理: obsidian://notes/RAG 原理.md
  - Ollama 配置: obsidian://notes/Ollama 配置.md
  ...
```

**如果得到错误而非这个结果，先排查最常见的两类原因**：

- **`FileNotFoundError`**：`server.py` 中的 `VAULT_PATH` 变量指向的目录不存在。用 `ls ~/Documents/Obsidian/Vault/.obsidian` 确认你实际的 vault 位置，然后修改 `VAULT_PATH`。
- **`ModuleNotFoundError: No module named 'mcp'`**：你执行 `test_client.py` 时没有激活虚拟环境，或者忘记 `pip install mcp`。执行 `source venv/bin/activate && pip list | grep mcp` 确认。

这个脚本在底层做了和 Cursor 完全相同的事情——通过 MCP 协议连接到 Server 并拉取资源列表。如果正确输出笔记 URI 列表，说明 MCP 通信链路畅通，可以继续配置 IDE。如果报错 `FileNotFoundError` 或连接超时，先检查 `server.py` 中的 `VAULT_PATH` 是否正确，以及 Python 虚拟环境是否已激活。

## 把知识库变成服务——搭建 Obsidian MCP Server

### 技术选型：Python 独立进程 vs TypeScript 插件

Obsidian 插件基于 TypeScript，可以调用 `app.vault` API 直接访问所有笔记。但 MCP Server 运行在 Obsidian 进程外部，不需要也不应该依赖 Obsidian 内部 API——它是一个独立的服务进程。选择 Python 实现基于以下理由：

1. **MCP Python SDK 成熟度**：`mcp` 包的 Python 实现比 TypeScript 侧更稳定，且与本章后续脚本（watchdog、LangChain 集成）共享同一语言生态。
2. **Markdown 解析优势**：Python 的 `python-frontmatter` 可以一行代码提取 YAML 头，`re` 标准库处理双链正则匹配——不需要额外学习 Node.js 生态中的对应库。
3. **可读性**：课程受众只需基础的编程概念，Python 语法的认知负担低于 TypeScript 的异步模型和模块系统。

如果你后续想开发一个运行在 Obsidian 内部的集成方案，可查阅 Obsidian Plugin API 文档（见本章参考文献），但本章采用 Python 独立进程方案。

### 环境准备

基于第 4 章已完成的本地环境，确认以下条件：

```bash
# Python ≥ 3.10
python3 --version

# Obsidian vault 路径存在（替换为你的实际路径）
ls ~/Documents/Obsidian/Vault/.obsidian
```

创建独立工作目录——Server 代码不要放在 vault 内部，避免污染知识库：

```bash
mkdir -p ~/obsidian-mcp-server
cd ~/obsidian-mcp-server
python3 -m venv venv
source venv/bin/activate  # Windows 用户: venv\Scripts\activate
```

安装依赖：

```bash
pip install mcp frontmatter watchdog lancedb pyarrow
```

验证成功安装：

```bash
python3 -c "import mcp; import frontmatter; import watchdog; import lancedb; print('OK')"
# 预期输出: OK
```

### 最小可用 MCP Server 实现

以下代码实现了一个能列出笔记、读取笔记、按关键词搜索的 Obsidian MCP Server。写入 `~/obsidian-mcp-server/server.py`：

```python
#!/usr/bin/env python3
"""
Obsidian MCP Server - 最小可用版本
功能：暴露知识库笔记为 MCP Resources，支持全文搜索工具。
使用 MCP Python SDK 的 stdio 传输。
"""

import os
import json
import re
from pathlib import Path
import frontmatter

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationCapabilities
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
)

# ===== 配置 =====
VAULT_PATH = os.path.expanduser("~/Documents/Obsidian/Vault")
if not os.path.isdir(VAULT_PATH):
    raise FileNotFoundError(
        f"Vault 路径不存在: {VAULT_PATH}。请修改 server.py 中的 VAULT_PATH。"
    )

# ===== MCP Server 实例 =====
server = Server("obsidian-mcp-server")

# ===== 辅助函数 =====

def list_notes(vault_path: str) -> list[dict]:
    """遍历 vault 中所有 .md 文件，返回笔记元数据列表（不含正文）。"""
    notes = []
    for md_file in Path(vault_path).rglob("*.md"):
        # 跳过 .obsidian 配置目录和 .trash 回收站
        if ".obsidian" in md_file.parts or ".trash" in md_file.parts:
            continue
        rel_path = md_file.relative_to(vault_path)
        stat = md_file.stat()
        notes.append({
            "path": str(rel_path),
            "title": md_file.stem,
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return notes


def parse_note(file_path: Path) -> dict:
    """解析单个 .md 文件，提取 frontmatter、正文和双链列表。"""
    try:
        post = frontmatter.load(file_path)
        meta = dict(post.metadata)
        body = post.content
    except Exception:
        meta = {}
        body = file_path.read_text(encoding="utf-8", errors="ignore")

    # 提取正文中所有 [[wikilink]]（不含别名和锚点）
    wikilinks = re.findall(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]", body)

    return {
        "title": file_path.stem,
        "frontmatter": meta,
        "body": body,
        "wikilinks": list(set(wikilinks)),
    }


def search_vault(vault_path: str, query: str) -> list[dict]:
    """全文搜索 vault，返回匹配笔记路径和上下文片段（最多 20 条）。"""
    # 简化实现：小写全文匹配。未支持 Obsidian 搜索语法的完整解析。
    terms = query.lower().split()
    results = []

    for md_file in Path(vault_path).rglob("*.md"):
        if ".obsidian" in md_file.parts or ".trash" in md_file.parts:
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            lower_text = text.lower()
        except Exception:
            continue

        if all(term in lower_text for term in terms):
            rel_path = md_file.relative_to(vault_path)
            # 提取第一个关键词的前后 80 字符作为片段
            match_pos = lower_text.find(terms[0])
            start = max(0, match_pos - 80)
            end = min(len(text), match_pos + 80)
            snippet = text[start:end]

            results.append({
                "file": str(rel_path),
                "snippet": snippet.strip(),
                "match_position": match_pos,
            })

    results.sort(key=lambda x: x["match_position"])
    return results[:20]


# ===== MCP Handlers =====

@server.list_resources()
async def handle_list_resources():
    """返回 vault 中所有笔记的 Resource 列表。"""
    resources = []
    for note in list_notes(VAULT_PATH):
        uri = f"obsidian://notes/{note['path']}"
        resources.append(
            Resource(
                uri=uri,
                name=note["title"],
                description=f"笔记: {note['path']} ({note['size']} bytes)",
                mimeType="text/markdown",
            )
        )
    return resources


@server.read_resource()
async def handle_read_resource(uri: str):
    """根据 URI 返回对应笔记的完整内容。"""
    rel_path = uri.replace("obsidian://notes/", "")

    # 关键安全防线：路径遍历防护
    note_path = (Path(VAULT_PATH) / rel_path).resolve()
    if not note_path.is_relative_to(Path(VAULT_PATH).resolve()):
        raise ValueError(f"非法路径: {rel_path}")

    if not note_path.exists():
        raise FileNotFoundError(f"笔记不存在: {rel_path}")

    note = parse_note(note_path)

    # 构建结构化返回：先 frontmatter，再正文，最后双链列表
    parts = []
    if note["frontmatter"]:
        parts.append("---")
        for k, v in note["frontmatter"].items():
            parts.append(f"{k}: {v}")
        parts.append("---\n")
    parts.append(note["body"])
    if note["wikilinks"]:
        parts.append("\n## 双链引用\n")
        for link in note["wikilinks"]:
            parts.append(f"- [[{link}]]")

    return [TextContent(type="text", text="\n".join(parts), uri=uri)]


@server.list_tools()
async def handle_list_tools():
    return [
        Tool(
            name="search_notes",
            description="在 Obsidian vault 中全文搜索笔记，返回匹配文件路径和上下文片段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，用空格分隔多词（逻辑 AND）"
                    }
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "search_notes":
        query = arguments.get("query", "")
        results = search_vault(VAULT_PATH, query)
        return [TextContent(
            type="text",
            text=json.dumps(results, ensure_ascii=False, indent=2),
        )]
    raise ValueError(f"未知工具: {name}")


# ===== 启动入口 =====

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationCapabilities(
                sampling=None,
                experimental=None,
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### 代码中的关键设计

**`@server.list_resources()` 装饰器**：把 Python 函数注册为 MCP 协议中 `resources/list` 请求的处理器。当 Cursor 启动子进程并向其 stdin 发送 `resources/list` 的 JSON-RPC 消息时，`mcp` 库自动调用被装饰的函数，将其返回的 `Resource` 列表序列化后写回 stdout。

**异步处理 (`async def`)**：Python 的 `async def` 定义的是协程函数，调用它不会立即执行函数体，而是返回一个需要被事件循环调度的协程对象。在 MCP Server 中，所有 Handler 都是协程函数，允许在等待文件 I/O 时让出控制权——当 `handle_list_resources` 正在等待磁盘读取一个巨大 vault 的文件列表时，事件循环可以转而处理另一个已到达的请求（例如心跳检测），而不是把整个进程卡住直到文件列表读完。即使当前搜索实现是同步的，异步包装为后续扩展（如同时搜索多个目录、接入外部图谱数据库）保留了空间。可以做一个快速对比：假设你有一个普通的同步 `def` 函数调用了 `time.sleep(2)` 来模拟慢速磁盘读取，在这 2 秒内程序无法做任何其他事情；而如果改用 `await asyncio.sleep(2)`，事件循环可以在这 2 秒内处理其他并发请求。

**URI 设计**：`obsidian://notes/{rel_path}` 是自定义 scheme，将 vault 中每个 `.md` 文件唯一映射为一个可寻址的 Resource。客户端通过调用 `resources/read` 并传入这个 URI 来获取笔记内容，就像浏览器通过 URL 获取网页。需要留意的是，这个 URI 并非操作系统注册过的标准 scheme——如果你在浏览器或终端中输入它，操作系统会提示无法识别。它只在 MCP 会话内有效。一个扩展方向是为你的机器注册自定义协议处理器，使点击 URI 时能直接跳转到 Obsidian 打开对应笔记；这超出了本章范围，但你可以在第 9 章的工作流闭环中重新审视这个想法。

**安全防线——`is_relative_to` 检查**：`handle_read_resource` 中的这一行是整个 Server 最关键的安全代码。如果删除它，攻击者可以构造 URI `obsidian://notes/../../../etc/passwd`，使得最终路径跳出 vault 目录，指向系统敏感文件。`is_relative_to` 强制保证最终路径一定以 `VAULT_PATH` 为前缀，任何 `../` 逃逸尝试都会被拦截。为了让你直观感受这一防御的效果：假设你的 `VAULT_PATH` 是 `/home/user/vault`，攻击者发送 URI `obsidian://notes/../../../etc/shadow`，拼接后的路径经 `resolve()` 后为 `/etc/shadow`，而 `is_relative_to('/home/user/vault')` 判断为 `False`，Server 立即抛出异常，不会泄露任何文件。你可以亲自在终端做一个受控实验来观察这一防御：在 `test_client.py` 中，尝试调用 `session.read_resource("obsidian://notes/../../../etc/hosts")`，观察 Server 抛出的错误信息，确认防御已生效。注意：这只是一个观察实验，不要试图读取你无权访问的文件。

**搜索函数的局限性——这是一个边界**：当前 `search_vault` 使用最朴素的小写全文匹配。它无法处理以下情况：
- 搜索 `apple` 会匹配到 `pineapple`，因为匹配前没有做词边界检测
- 不支持 `tag:` 或 `file:` 等 Obsidian 语法
- 对大型 vault 效率低（每次搜索都要遍历所有 .md 文件）

为什么选择这个简化的实现？因为最朴素的版本让你看清 Server 的骨架：收到请求 → 遍历文件 → 匹配关键词 → 返回结果。所有优化都可以在这个骨架上逐层叠加——加正则做词边界、解析 frontmatter 做标签索引、引入缓存加速——而不会改变 Server 与 Client 的交互契约。

### 验证 Server 启动

在终端中手动运行：

```bash
cd ~/obsidian-mcp-server
source venv/bin/activate
python3 server.py
```

Server 会启动并等待 stdin 输入——这是正常状态，它正在等待客户端通过 stdio 发送初始化消息。按 `Ctrl+C` 退出。如果报错 `FileNotFoundError: Vault 路径不存在`，请修改 `VAULT_PATH` 为你的实际 vault 路径。

**一对一的限制与反例**：MCP 的 stdio 传输在设计上是严格的一对一连接——一个 Server 进程同时只能服务一个 Client，因为它的 stdin/stdout 正是该进程的生命线。如果你在终端运行 `server.py`，然后尝试从 Cursor 也连接同一个路径，Cursor 会启动另一个独立的 `server.py` 子进程，两个 Server 实例互不干扰。但如果你手动启动了 `server.py` 保持运行，再试图用 `test_client.py` 连接它，连接会失败，因为前者的 stdin/stdout 已经被终端占用，不是可供新父进程管道连接的形态。正确的模式是永远让 Client 作为父进程来启动 Server 子进程。

## 让 IDE 连接你的第二大脑——集成到 Cursor 与 Claude Code

### 集成到 Cursor

Cursor（版本 ≥ 0.42）原生支持 MCP。

1. 打开 Cursor Settings → 搜索 `mcp` → 点击 `Add new MCP server`。
2. 填写配置：
   - **Name**: `obsidian`
   - **Type**: `command`
   - **Command**: 替换为用户实际路径——

     **macOS/Linux**:
     ```bash
     /Users/你的用户名/obsidian-mcp-server/venv/bin/python3 /Users/你的用户名/obsidian-mcp-server/server.py
     ```

     **Windows**:
     ```cmd
     C:\Users\你的用户名\obsidian-mcp-server\venv\Scripts\python.exe C:\Users\你的用户名\obsidian-mcp-server\server.py
     ```

3. 保存后 Cursor 会自动启动子进程并完成 `initialize` 握手。

**验证集成成功**：在 Cursor 的 AI 聊天框（`Cmd+L` / `Ctrl+L`）中输入：

```
请使用 obsidian MCP 工具，在我的笔记里搜索关于 RAG 的内容，并引用笔记原文回答。
```

如果 Cursor 调用了 `search_notes` 并返回了你笔记中的实际片段，回答中出现了你熟悉的笔记引用——而不是 AI 的通用知识——则集成成功。如果报错 “MCP server not found”，请检查：
- 虚拟环境的 Python 路径是否完全正确（用 `which python3` 或 `where python` 确认）。
- `server.py` 中的 `VAULT_PATH` 是否指向包含 `.obsidian` 文件夹的真实目录。
- 在终端中单独执行一次命令，确认 Server 能进入等待状态而不报错。

### 集成到 Claude Code

Claude Code（Anthropic 的命令行 AI 助手）同样原生支持 MCP。编辑 `~/.claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "/Users/你的用户名/obsidian-mcp-server/venv/bin/python3",
      "args": [
        "/Users/你的用户名/obsidian-mcp-server/server.py"
      ]
    }
  }
}
```

重启 Claude Code 后，使用 `@obsidian` 前缀触发：

```
@obsidian 搜索我的笔记中关于 GraphRAG 实体解析的结论
```

### 集成到 Windsurf

Windsurf 同样内置 MCP 客户端支持。在 Windsurf 中启用 MCP 的方式与 Cursor 几乎完全一致：

1. 打开 Windsurf 设置，搜索 `MCP`，进入 MCP 配置界面。
2. 点击 `Add Server`，选择 `Command` 方式。
3. 填写以下参数：
   - **Name**: `obsidian`
   - **Command**: 替换为用户实际路径——
     **macOS/Linux**:
     ```bash
     /Users/你的用户名/obsidian-mcp-server/venv/bin/python3 /Users/你的用户名/obsidian-mcp-server/server.py
     ```
     **Windows**:
     ```cmd
     C:\Users\你的用户名\obsidian-mcp-server\venv\Scripts\python.exe C:\Users\你的用户名\obsidian-mcp-server\server.py
     ```

保存后，在 Windsurf 的 AI 对话框中即可使用 `@obsidian` 工具搜索和引用笔记。如果你已经完成了 Cursor 的配置，Windsurf 只需复用相同的 server 启动命令，无需任何额外修改。

## 当笔记发生变化时——自动化同步外部向量库

MCP Server 解决了“外部工具主动读取”的问题，但还有另一半：你在 Obsidian 里写完新笔记之后，那些依赖你笔记数据的外部系统（比如第 4 章搭建的本地 RAG 管道）怎么知道内容更新了？

答案是：用文件监听 + 自动增量索引。架构如下：

```text
Obsidian Vault (文件系统)
    │
    │  watchdog 监听 .md 文件变动
    ▼
Python Watcher 脚本
    │
    │  解析 → 分块 → 调用 Ollama embedding → 写入向量库
    ▼
LanceDB 向量数据库 (纯本地、零服务进程)
    │
    │  API 查询
    ▼
你的 RAG 应用、MCP Client 等检索端
```

这个脚本与 MCP Server 保持独立运行，以便于单独调试。

### 防抖——为什么不能每次保存都立刻同步

如果你在编辑一条长笔记，Obsidian 一秒钟内自动保存了 5 次。如果没有防抖，同步脚本会忠实地触发 5 次完整流程：读取文件 → 分块 → 调用 Ollama embedding API → 写入 LanceDB。这不仅浪费 CPU 和 I/O，还可能把 Ollama 的 embedding 端点冲垮（本地模型也有吞吐上限），导致部分写入失败，在向量库中留下中间状态的脏数据。

**直观感受防抖效果**：你可以打开两个终端窗口，在窗口 A 运行 `python3 sync_vector.py` 开始监听，然后在窗口 B 中连续执行多次 `touch ~/Documents/Obsidian/Vault/test.md`（模拟快速连续保存）。观察窗口 A，你会发现它并不会每 `touch` 一次就打印一条 `[SYNC]`，而是等待所有 `touch` 停止超过 2 秒后，才输出一条同步日志——中间那些瞬间变动被合并为一次处理。这就是防抖的价值：用极短的等待省去大量重复计算。

防抖的策略是：**等文件“静止”后再处理**。具体的代码实现是用一个 `_pending` 字典记录每个文件最后一次变动的时间戳，然后在一个独立的 `flush_pending` 循环中每隔一秒检查一次：有哪些文件距离最后一次变动已经超过了 2 秒？这些文件才算“编辑完成”，可以安全地同步。连续 5 次快速保存带来的 5 次时间戳更新，最终只会触发最后一次同步。

```python
# 防抖机制的核心代码逻辑
_pending = {}  # {文件路径: 最后一次变动时间戳}

def on_modified(self, event):
    # 每次文件变动时，只更新这个时间戳
    self._pending[event.src_path] = time.time()

def flush_pending(self):
    # 每秒检查一次，处理静止超过 2 秒的文件
    for path_str, last_change in list(self._pending.items()):
        if time.time() - last_change > 2.0:
            self._sync_file(path_str)  # 真正执行同步
            del self._pending[path_str]  # 从待处理列表中移除
```

**2 秒的边界讨论**：对于常规笔记编辑，2 秒够用。但如果你正在使用批量导入（一次性将外部 Markdown 文件夹复制进 vault），数百个文件同时生成，`_pending` 缓冲区会快速膨胀——可将延迟延长至 5 秒，或改为批处理模式。如果你正在编辑超过 10000 字的巨型笔记，保存耗时可能接近 1 秒，可将延迟保守设为 3 秒。

另一个需要处理的边界是 **Ollama 服务未启动**的情况。如果脚本运行时 Ollama 未运行，`get_embedding` 函数会捕获异常并打印警告，不会崩溃，但 `_pending` 缓冲区中的文件会持续堆积。你可以先启动 Ollama（`ollama serve`），完成后脚本会把积压文件逐一处理。

**一个必要的反例：不要设置防抖为 0**。如果你把 `flush_pending` 中的 `2.0` 改为 `0`，每次文件变化都会被立即处理。来模拟一下后果：在 Obsidian 里打出一句话，Obsidian 自动保存，触发同步；你紧接着敲下下一句话，又触发一次同步；你删除一段，再触发。结果是 30 秒内触发十几次完整的分块+embedding+写库流程，Ollama 队列被占满，终端满屏的 `[SYNC]` 日志混在一起无法分辨哪次是最终状态。更糟的是，如果 Ollama 是 spinning up 刚加载模型，前几次 embedding 调用会超时，向量库里留下的全是空的或错误的分块。

### 实现：watch + sync 脚本

写入 `~/obsidian-mcp-server/sync_vector.py`：

```python
#!/usr/bin/env python3
"""
Obsidian Vault → LanceDB 向量库自动同步脚本
使用 watchdog 监听 .md 文件变动，防抖后执行分块与向量化。
"""

import os
import time
import hashlib
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import frontmatter

# ===== 配置 =====
VAULT_PATH = os.path.expanduser("~/Documents/Obsidian/Vault")
VECTOR_DB_PATH = os.path.expanduser("~/obsidian-mcp-server/vector_store")

# ===== 分块策略 =====
def chunk_markdown(body: str, max_size: int = 800) -> list[str]:
    """按段落切分 Markdown 正文，保留段落完整性。超长段落按句子切分。"""
    chunks = []
    paragraphs = body.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < max_size:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            if len(para) > max_size:
                # 超长段落按句号分切
                sentences = para.replace("。", "。|||").split("|||")
                sub = ""
                for s in sentences:
                    if len(sub) + len(s) < max_size:
                        sub += s
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                if sub:
                    chunks.append(sub)
            else:
                current = para

    if current:
        chunks.append(current)
    return chunks


# ===== 向量化 =====
def get_embedding(text: str) -> list[float]:
    """调用 Ollama embedding API（OpenAI 兼容格式）。"""
    import urllib.request
    data = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception as e:
        print(f"[WARN] Embedding 失败（Ollama 是否在运行?）: {e}")
        return []


# ===== LanceDB 操作 =====
import lancedb
import pyarrow as pa

def init_db():
    """初始化 LanceDB，创建 notes 表（若不存在）。"""
    db = lancedb.connect(VECTOR_DB_PATH)
    if "notes" not in db.table_names():
        db.create_table(
            "notes",
            schema=pa.schema([
                pa.field("id", pa.string()),
                pa.field("content", pa.string()),
                pa.field("file_path", pa.string()),
                pa.field("modified", pa.float64()),
                pa.field("embedding", pa.list_(pa.float32(), 768)),
            ]),
        )
    return db


def upsert_chunk(db, chunk_id: str, content: str, file_path: str, modified: float):
    """插入或替换一个分块到向量库。"""
    emb = get_embedding(content)
    if not emb:
        return False
    table = db.open_table("notes")
    table.delete(f"id = '{chunk_id}'")
    table.add([{
        "id": chunk_id,
        "content": content,
        "file_path": file_path,
        "modified": modified,
        "embedding": emb,
    }])
    return True


def remove_file_chunks(db, file_path: str):
    """删除某笔记的所有分块。"""
    table = db.open_table("notes")
    safe_path = file_path.replace("'", "''")
    table.delete(f"file_path = '{safe_path}'")


# ===== watchdog Handler =====
class VaultChangeHandler(FileSystemEventHandler):
    def __init__(self, db):
        self.db = db
        self._pending = {}  # 防抖缓冲区

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        if ".obsidian" in event.src_path or ".trash" in event.src_path:
            return
        self._pending[event.src_path] = time.time()

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        rel_path = str(Path(event.src_path).relative_to(VAULT_PATH))
        remove_file_chunks(self.db, rel_path)
        print(f"[SYNC] 已删除: {rel_path}")

    def flush_pending(self):
        """处理已经静止 2 秒以上的文件。"""
        now = time.time()
        to_process = []
        for path_str, last_change in list(self._pending.items()):
            if now - last_change > 2.0:
                to_process.append(path_str)
                del self._pending[path_str]

        for path_str in to_process:
            if not os.path.exists(path_str):
                continue
            self._sync_file(path_str)

    def _sync_file(self, path_str):
        rel_path = str(Path(path_str).relative_to(VAULT_PATH))
        try:
            post = frontmatter.load(path_str)
            body = post.content
        except Exception as e:
            print(f"[WARN] 无法解析 {rel_path}: {e}")
            return

        chunks = chunk_markdown(body)
        if not chunks:
            return

        remove_file_chunks(self.db, rel_path)
        mtime = os.path.getmtime(path_str)
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{rel_path}#{i}".encode()).hexdigest()
            ok = upsert_chunk(self.db, chunk_id, chunk, rel_path, mtime)
            if ok:
                print(f"[SYNC] 已索引: {rel_path} (chunk {i+1}/{len(chunks)})")
            else:
                print(f"[WARN] 索引失败: {rel_path} (chunk {i+1})")


def start_watching():
    if not os.path.isdir(VAULT_PATH):
        print(f"[ERROR] Vault 路径不存在: {VAULT_PATH}")
        return

    db = init_db()
    handler = VaultChangeHandler(db)
    observer = Observer()
    observer.schedule(handler, VAULT_PATH, recursive=True)
    observer.start()
    print(f"[WATCH] 开始监听: {VAULT_PATH}")

    try:
        while True:
            time.sleep(1)
            handler.flush_pending()
    except KeyboardInterrupt:
        observer.stop()
        print("\n[WATCH] 已停止")
    observer.join()


if __name__ == "__main__":
    start_watching()
```

### 运行与验证

```bash
python3 sync_vector.py
```

保持脚本运行，在 Obsidian 中新建一条笔记并输入内容。约 2-3 秒后终端应显示：

```
[SYNC] 已索引: 新笔记.md (chunk 1/1)
```

修改该笔记并保存，同样会触发一次重新索引。如果终端只输出 `[WATCH] 开始监听` 而无后续同步日志，请检查 vault 路径是否正确、Ollama 是否正在运行。

### 分块策略的选择：段落 vs AST

第 2 章介绍了基于 AST 的递归切分——按 H1/H2/H3 标题构建语义树来切分。但在实时同步脚本中，本章选择了更简单的**段落切分**：

- **性能**：段落切分只需按 `\n\n` 分割字符串，不依赖解析库，速度远快于 AST 构建。
- **容错**：用户在 Obsidian 里写草稿时 Markdown 结构可能不完整（忘闭合代码块、标题跳级）。AST 解析器遇到这些格式错误容易崩溃，而段落切分几乎永不失败。

代价是：如果某条笔记包含长达 2000 字的无空行段落，段落切分会退化为句子切分，可能拆散紧密关联的句子。对于个人知识库规模，这通常不是致命问题——检索时相邻块也会一起召回。如果你需要极致精度，可以把 `chunk_markdown` 替换为第 2 章的 AST 切分函数（需要额外安装 `mistune` 或 `markdown-it-py`）。

### 为什么是 LanceDB

| 方案 | 部署模式 | 查询性能 | 适用场景 |
| --- | --- | --- | --- |
| **LanceDB** | 纯嵌入式，零服务进程 | 高（列式存储） | 个人知识库（数千条笔记） |
| Chroma | 嵌入式 | 中（万条后插入降速） | 快速 PoC |
| Qdrant | 需独立服务守护 | 极高（gRPC/REST） | 生产级部署、多用户并发 |

对于本章“本地个人开发机”的场景，LanceDB 是最优解：它的数据和索引都在 `~/obsidian-mcp-server/vector_store/` 目录下，可以和笔记一起备份，不需要任何额外进程。当你未来笔记量增长到数万条且需要毫秒级并发查询时，再考虑迁移到 Qdrant。

## 保护你的知识库——安全边界与注意事项

1. **敏感目录过滤**：代码中已跳过 `.obsidian` 和 `.trash`。如果你有私人日记目录（如 `Journal/私人/`），请在 `list_notes` 和 `search_vault` 中增加排除条件。
2. **路径遍历防护**：`handle_read_resource` 中的 `is_relative_to` 检查是绝对不能删除的安全底线。它阻止 `../../../etc/passwd` 这类攻击。去掉它，攻击者可以读取你机器上的任意文件。
3. **只读优先**：当前 Server 只暴露了 Resources 读和搜索 Tool，没有写操作。在第 9 章的 Agentic 闭环需要自动创建笔记之前，保持只读是最安全的姿势。
4. **stdio 隐私优势**：所有数据只在你的本机两个进程之间流转，永不触及网络。除非你有明确的远程访问需求（如手机上的工具要访问台式机的知识库），否则始终使用 stdio，不要切换到 HTTP 传输。

## 练习

### 练习一：用客户端脚本验证资源列表

编写一个 MCP Client 脚本，调用 `initialize` 和 `resources/list`，打印出 vault 中所有笔记的 URI 列表。对照你的 Obsidian 文件管理器，确认二者一一对应。

### 练习二：扩展搜索——实现标签过滤

修改 `search_vault` 函数，支持 `tag:标签名` 语法。例如搜索 `"tag:rag BM25"` 应只返回 frontmatter 中 tags 包含 `rag` 且正文包含 `BM25` 的笔记。

**测试反例**：构造一条笔记正文含 `BM25` 但 tags 不含 `rag`，另一条 tags 含 `rag` 但正文不含 `BM25`。执行搜索后，验证结果只包含同时满足两个条件的笔记。

### 练习三：同步脚本的检索验证

确保 `sync_vector.py` 已索引至少 10 条笔记。编写一个查询脚本，调用 LanceDB 的向量检索 API，搜索与你的查询最相似的 5 个分块。检查返回结果是否相关——如果不理想，尝试调整 `max_size` 参数后重新同步。

**调用示例**（以下代码可保存为 `query_vector.py` 直接运行）：

```python
#!/usr/bin/env python3
"""查询 LanceDB 向量库，返回与查询最相似的 5 个分块"""
import os
import json
import urllib.request
import lancedb

# 1. 获取查询的 embedding（复用 sync_vector.py 的 get_embedding 逻辑）
def get_embedding(text: str) -> list[float]:
    data = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["embedding"]

# 2. 连接 LanceDB，打开 notes 表
db = lancedb.connect(os.path.expanduser("~/obsidian-mcp-server/vector_store"))
table = db.open_table("notes")

# 3. 执行向量检索
query = "你的查询内容（例如：BM25 调参结论）"
query_vec = get_embedding(query)
results = table.search(query_vec).limit(5).to_list()

# 4. 输出结果
for i, row in enumerate(results):
    print(f"--- 结果 {i+1} ---")
    print(f"文件: {row['file_path']}")
    print(f"内容: {row['content'][:200]}...")
    print(f"相似度: {row['_distance']:.4f}")
    print()
```

**验收标准**：
- 运行 `python3 query_vector.py` 后，终端输出 5 个分块及其来源文件路径和相似度得分。
- 若结果与查询明显不相关，逐步调整 `sync_vector.py` 中的 `max_size` 参数（如改为 400 或 1200），重新同步后再次验证，直到结果合理。

### 练习四：IDE 中的知识引用体验

在 Cursor 或 Claude Code 中，让 AI 助手撰写一段关于“RRF 融合算法”的技术说明，要求它引用你笔记中的实际结论，而不是通用知识。对比同一任务在不连接 MCP 时的回答差异，并记录至少一个你希望 Server 能支持但目前尚未实现的能力（例如反向链接查询、图谱邻居查询）。

## 自检

1. MCP 协议解决的核心集成问题是什么？和直接让外部工具读本地 Markdown 文件有何本质区别？
2. Resources、Tools、Prompts 各自对应什么交互模式？本章的 Server 暴露了哪些？
3. `handle_read_resource` 中的路径遍历检查为什么是必须的？如果去掉它，攻击者能做什么？
4. `sync_vector.py` 的防抖机制解决了什么问题？如果防抖延迟设为 0 秒会发生什么？
5. 本章为什么选择 LanceDB 而不是 Chroma 或 Qdrant？在什么场景下你会转而使用 Qdrant？
6. MCP 使用 stdio 通信的隐私优势是什么？什么情况下你才会选择 HTTP 传输？

## 参考文献

- [Model Context Protocol Specification (2025-06-18)](https://modelcontextprotocol.io/specification/2025-06-18)：MCP 协议官方规范，定义 Resources、Tools、Prompts 的语义与交互流程。
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)：Python 实现的 MCP Server 与 Client SDK。
- [Ollama OpenAI Compatibility](https://docs.ollama.com/api/openai-compatibility)：Ollama embedding API 文档，本章同步脚本依赖此端点。
- [LanceDB Documentation](https://lancedb.github.io/lancedb/)：LanceDB 列式向量数据库 Python API 参考。
- [watchdog Documentation](https://python-watchdog.readthedocs.io/)：Python 文件系统事件监听库文档。
- [Obsidian Plugin API](https://docs.obsidian.md/Reference/TypeScript+API/Plugin)：理解 vault 内部数据结构的官方参考（本章未直接调用）。

回顾一下：MCP 协议已经把 Obsidian 知识库从被动仓库变成了可被外部工具查询的服务——IDE 现在能主动向你的笔记提问。但这个服务要起作用，知识库必须与外部向量数据库保持同步，否则外部 RAG 管线用的永远是过时数据。`sync_vector.py` 解决的就是这个同步问题，它通过文件监听、防抖和增量向量化，在笔记被修改的瞬间就将变化推送到 LanceDB 中。这两个组件（MCP Server 与同步脚本）构成了知识库的“输出层”：一个响应外部请求，一个主动推送更新。目前你有了完整的“外部读取”链路，但知识库还缺一项能力：自动根据课题检索、生成并写回新笔记。这项能力——Agentic 闭环——是下一章的核心任务，我们将构建一条从“提问”到“自动写回笔记及双链”的完整流水线，完成笔记的自动写回与双链创建。
