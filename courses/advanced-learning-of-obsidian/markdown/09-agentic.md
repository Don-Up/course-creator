# 第 9 章 知识库评估、维护与 Agentic 工作流闭环

> 预计学习时间：2.5 小时  
> 一句话总结：本章将你从第4章到第8章积累的所有组件——本地 RAG、GraphRAG、MCP Server、外部向量库——组装成一个能自动评估、修复并生成笔记的工作流。

---

## 9.0 本章前置：你应当已经熟悉的概念与组件

在动手之前，请先回顾前几章的关键组件。如果你对其中任何一个感到模糊，请花几分钟回看对应章节的“理解检查”部分。

- **嵌入（Embedding）**：将一段文字转换为高维数值向量的过程。语义相近的文字，向量在空间中的距离也近。本章依赖 `nomic-embed-text` 模型完成这一转换，每次调用 Ollama 的 `/api/embed` 端点都会返回一个固定长度的数字列表。向量的“相似度”通常用余弦相似度衡量，数值从 -1 到 1，越接近 1 越相似。

- **LanceDB**：一个纯文件存储的向量数据库，你已经在第 8 章用它保存了笔记的分块及其嵌入。它的核心操作只有三个：建表、插入向量记录、按向量相似度搜索。本章的检索步骤会直接调用 LanceDB 的 `search()` 方法，无需其他服务进程。

- **Ollama 本地推理**：你本地的 `http://localhost:11434` 既提供嵌入模型也提供对话模型。本章使用 `qwen2.5:7b` 作为生成模型，`nomic-embed-text` 作为嵌入模型。两者的调用方式相似，只是端点不同：`/api/generate` 用于文本生成，`/api/embed` 用于向量化。

- **第 6 章 GraphRAG 中的实体与关系**：你在 LightRAG 实验中抽取的实体三元组和双链关系，是本章评估和闭环生成的重要数据源。如果图索引已过期或未正确构建，检索将退化为纯向量搜索，影响上下文多样性。

- **MCP Server**：第 8 章用 Python 搭建的服务器，对外暴露了 `search_notes` 工具。本章的 Agent 可以直接复用其搜索逻辑，或者直接调用 LanceDB API 获得相同效果。MCP 的只读特性将在本章被突破，因为 Agent 需要向 Obsidian 写入新笔记。

- **RAGAS**：用于评估检索增强生成系统的框架，本章的重点工具。它不依赖人工打分的“标准答案”，而是通过大模型自己判断答案质量。它的三个核心指标——忠实度、答案相关性、上下文精准度——将在 9.3 节详细拆解。

现在确认你已经具备以下运行条件：Ollama 服务正常响应、LanceDB 索引目录存在且不为空、第 6 章的 LightRAG 图索引仍可加载（如果你计划结合 GraphRAG 做检索）。如果一切就绪，我们就能开始第一个切片。

---

## 9.1 交付契约：这章到底要造什么

在进入操作之前，先明确边界。你已拥有一个能跑的本地知识库系统：笔记存于 Obsidian，向量索引在 LanceDB，双链图谱和实体关系可从 LightRAG 索引查询，MCP Server 可对外暴露这些能力。但它目前只具备基础能力，缺少评估、维护和自动生成。

本章要交付的是一个 **Agentic 闭环**，由三个纵向切片组成：

| 切片 | 系统或用户得到什么 | 如何验证 | 停止条件 |
|------|---------------------|----------|----------|
| 评估 | 当前知识库的 RAG 质量分数（忠实度、答案相关性、上下文精准度） | 运行评估脚本，输出 RAGAS 格式报告 | 三项指标均返回 0-1 之间的有效分数 |
| 维护 | 可执行的垃圾回收规则和防退化脚本 | 运行维护脚本后，冗余笔记被标记、孤立笔记被列出 | 目标目录中的 `.trash` 候选减少到 0 |
| 闭环 | 输入一个课题，系统自行检索、生成草稿、创建 Obsidian 笔记并写回双链和 Tag | 在 Obsidian 中观察到新笔记文件及图谱中新增的连接 | 笔记文件包含至少一个 `[[双链]]` 和 Frontmatter `tags` |

**闭环切片的输出将直接实现第 8 章规划的目标**：扩展 MCP Server 能力边界，从只读跨越到可控写入。Agent 在 `Research` 子目录下创建结构化笔记，自动填充双链与标签，使知识库具备自动扩展的能力。它复用第 8 章的检索逻辑，但新增 `write_note` 写入步骤——这一步骤仅作用于 `Research/` 目录，不会触碰你手工撰写的笔记区域，以此规避误写风险。

**起始资产**：你目前拥有一个包含至少 20 篇笔记的 Obsidian Vault（积累了前 8 章的学习笔记即可），第 4 章部署的 Ollama 本地推理服务（`http://localhost:11434`），第 6 章通过 LightRAG 构建的图索引实体与关系数据，第 8 章的 MCP Server 和 LanceDB 向量库。

**范围外**：本章不讨论多用户协同编辑冲突、云端同步策略、Ollama 之外的其他推理引擎（如 LM Studio 或 vLLM），也不涉及生产级鉴权。

---

## 9.2 准备工作：让所有组件先跑起来

启动以下服务并逐一验证。每一条验证命令都要得到明确结果才能继续。

**Python 环境与依赖**

为了更好地管理依赖，请为本章创建独立的虚拟环境，并安装经测试的包版本：

```bash
python3 -m venv venv-ch9
source venv-ch9/bin/activate  # Windows 使用 venv-ch9\Scripts\activate
pip install lancedb ragas==0.1.20 datasets requests pyyaml
```

- `ragas==0.1.20`：本章代码基于此版本编写，API 稳定（`from ragas import evaluate` 与 `from ragas.metrics import faithfulness, answer_relevancy, context_precision` 可直接使用）。如果后续 RAGAS 大版本变化，你可能需要查阅官方迁移指南。
- `requests`：所有与 Ollama 的通信都使用 HTTP API，不依赖任何 LangChain 封装，因此无需安装 `langchain-community`。
- `pyyaml`：Agent 写回笔记时需要生成 YAML Frontmatter。

**服务状态检查清单**：

```bash
# 1. Ollama 服务
curl http://localhost:11434/api/tags
# 预期：返回 JSON 数组，包含已下载的模型列表

# 2. LanceDB 索引存在性
ls -la ~/obsidian-rag-data/lancedb/
# 预期：列出 .lance 目录文件，非空

# 3. MCP Server 连通性（在项目 venv 中执行）
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python server.py
# 预期：返回 tools 列表，包含 search_notes
```

如果任一检查不通过，回到第 4 章或第 8 章补全对应组件。本章所有后续操作都依赖这三者同时在线。

---

## 9.3 切片一：用 RAGAS 给知识库打分

### 9.3.1 为什么要评估？——先理解三个维度

你自己的检索系统能跑起来是一回事，它给出的答案“够不够好”是另一回事。RAGAS（Retrieval Augmented Generation Assessment）是专门衡量 RAG 系统质量的框架，它不依赖人工标注的“标准答案”，而是从三个维度进行量化：

**忠实度（Faithfulness）**：答案中的每一个断言，是否都能在检索到的上下文中找到依据？如果 LLM 凭空编了一个不存在于笔记中的概念，忠实度就会下降。

*可观察判据*：忠实度 1.0 意味着答案中每个事实陈述都对应上下文原文；0.5 意味着大约一半的陈述找不到出处。

**答案相关性（Answer Relevance）**：答案是否紧扣问题？一个很忠实但答非所问的回答——比如你问“RAFT 的前提是什么”，它忠实引用了你的 CAP 理论笔记——相关性会低。

*可观察判据*：相关性 1.0 意味着回答的所有段落都直接回应提问；0.3 意味着大量内容与问题无直接关联。

**上下文精准度（Context Precision）**：检索回来的上下文片段中，真正有用的比例有多高？如果召回了 5 个片段但只有 1 个相关，精准度只有 0.2。

*可观察判据*：精准度 1.0 意味着每个被召回的片段都是回答所需；低分意味着管道在“灌噪音”。

三者构成了闭环：**检索要精准，上下文要可用，生成要忠实且相关**。任何一环短板都会影响最终体验。

示例：一次真实打分

假设你的知识库中有两篇笔记：《CAP 理论》和《数据库事务隔离级别》。评估工具提出一个问题：“什么是读已提交隔离级别？”检索器从 LanceDB 返回了三个上下文片段：

1. 《数据库事务隔离级别》中关于读已提交的段落（真正相关）
2. 《CAP 理论》中关于一致性的段落（部分重叠但非直接答案）
3. 《数据库事务隔离级别》的另一段，讨论可重复读（不直接回答提问）

LLM 生成的答案包含了“读已提交允许事务读取其他事务已提交的数据”，这直接来源于片段 1；同时也提到了“一致性概念”，这部分来自片段 2，但与问题关联较弱。RAGAS 会计算出大约：忠实度 0.85（因为一致性部分确实在片段 2 中有依据），答案相关性 0.65（一致性部分拉低了聚焦度），上下文精准度 0.5（三个片段中只有第一个完全相关）。这个例子让你看到，即使答案部分正确，如果检索管道塞入了无关内容，整体得分仍会受损。

反例：虚假的高相关性

注意：答案相关性指标并非万能。如果 LLM 倾向于在每次回答中都加入大段与问题看似相关但实则空泛的总结（例如任何关于数据库的问题它都先写一段“数据库是存储数据的系统”），那么生成的答案变体在语义上仍会与原问题相近，导致相关性得分虚高。这种“安全话术”会掩盖模型实际并未深入回答具体问题的事实。避免的方法是在评估数据集中加入需要精确事实的问题，并检查低相关性条目是否符合直觉。如果直觉与分数矛盾，手动抽查 2-3 条生成的答案。

### 9.3.2 生成评估数据集

RAGAS 需要一组“问题—标准答案—上下文”三元组来运行。你不可能人工写几百条，这里采用策略：让 LLM 根据你的笔记内容自动生成评估问题。

在项目目录中创建 `eval/generate_eval_set.py`：

```python
import json, os, re
from pathlib import Path
import requests

VAULT_PATH = os.path.expanduser("~/Documents/Obsidian/Vault")
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"
OUTPUT_FILE = "eval_dataset.json"

def list_notes(vault: str, limit: int = 15) -> list:
    notes = []
    for root, _, files in os.walk(vault):
        for f in files:
            if f.endswith(".md") and not root.endswith((".trash", ".obsidian")):
                path = Path(root) / f
                notes.append({
                    "path": str(path),
                    "filename": f,
                    "content": path.read_text(encoding="utf-8")[:3000]
                })
    return notes[:limit]

def generate_qa(note: dict) -> list:
    prompt = f"""你是 RAG 评估用例生成器。阅读以下笔记，生成 2 个问题和对应的标准答案。问题应该需要理解笔记内容才能回答。返回纯 JSON 数组，每个元素包含 question 和 answer。

笔记文件名：{note['filename']}
内容：
{note['content'][:2000]}

仅返回 JSON，无其他文字。"""
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False
    })
    text = resp.json()["response"].strip()
    # 提取 JSON 数组
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return []

all_qa = []
for note in list_notes(VAULT_PATH):
    qas = generate_qa(note)
    for qa in qas:
        qa["source_note"] = note["filename"]
    all_qa.extend(qas)

Path(OUTPUT_FILE).write_text(json.dumps(all_qa, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"生成 {len(all_qa)} 条评估用例 → {OUTPUT_FILE}")
```

运行后检查 `eval_dataset.json` 是否包含至少 20 条问题。每条应有 `question`、`answer` 字段——这是 RAGAS 的输入。

**检验自动生成评估集的质量**

你让 LLM 生成的问题和答案可能包含“免费信息”——问题本身已经暗示了答案，或者答案只是复述问题。这会虚高评估分数。例如，生成器看到《CAP 理论》笔记后可能产出：“什么是 CAP 理论？”这样的问题过于宽泛。理想的评估问题应要求组合多处信息，比如：“如果系统牺牲了一致性以换取可用性，它违反了 CAP 的哪条保证？”运行 `generate_eval_set.py` 后，打开 `eval_dataset.json`，随机选取 5 条，检查：

- 问题是否包含笔记关键词（如“CAP”）而无需检索即可回答？若是，应改写为需要跨段落推理的形式。
- 答案是否直接复制了笔记中的大段原文？若是，将其压缩为一句话摘要，以检验答案相关性指标的区分度。

**练习**：手动修正上述 5 条中存在上述缺陷的用例，并记录你修改前后的差异。完成后再运行 9.3.3 的评估，观察三个指标的分数变化。这份练习让你理解：评估数据集的“难度”直接影响你对系统能力的判断。

### 9.3.3 运行 RAGAS 评估

确认已按照 9.2 节创建虚拟环境并安装 `ragas==0.1.20`、`datasets`、`requests`、`lancedb`。本章不再使用 LangChain 的任何封装，所有操作直接通过 HTTP API 和 LanceDB 原生接口完成，既简化依赖，也避免了不同库之间接口不一致的问题。

创建 `eval/run_ragas.py`：

```python
import json, requests, os
import lancedb
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision

OLLAMA_EMBED = "http://localhost:11434/api/embed"
OLLAMA_GENERATE = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"
LANCE_DIR = os.path.expanduser("~/obsidian-rag-data/lancedb")

def get_embedding(text: str) -> list:
    """调用本地 Ollama 嵌入服务，返回向量"""
    resp = requests.post(OLLAMA_EMBED, json={
        "model": EMBED_MODEL, "input": text
    })
    return resp.json()["embeddings"][0]

def search_lancedb(query: str, top_k: int = 3) -> list:
    """用查询向量在 LanceDB 中检索最相似的笔记片段"""
    db = lancedb.connect(LANCE_DIR)
    table = db.open_table("notes")
    q_emb = get_embedding(query)
    results = table.search(q_emb).limit(top_k).to_list()
    return [r["content"] for r in results]

def generate_answer(question: str, contexts: list) -> str:
    """根据检索上下文生成答案"""
    ctx_str = "\n---\n".join(contexts)
    prompt = (
        "根据以下上下文回答问题。如果上下文信息不足，请说明。\n\n"
        f"上下文：\n{ctx_str}\n\n问题：{question}"
    )
    resp = requests.post(OLLAMA_GENERATE, json={
        "model": MODEL, "prompt": prompt, "stream": False
    })
    return resp.json()["response"].strip()

# 1. 加载评估集
with open("eval_dataset.json", "r", encoding="utf-8") as f:
    qa_pairs = json.load(f)

# 2. 对每个问题检索上下文并生成答案
questions, answers, contexts_list, ground_truths = [], [], [], []
for qa in qa_pairs[:20]:   # 先测 20 条
    ctx = search_lancedb(qa["question"])
    ans = generate_answer(qa["question"], ctx)
    questions.append(qa["question"])
    answers.append(ans)
    contexts_list.append(ctx)
    ground_truths.append(qa["answer"])

# 3. 构建 RAGAS 评估数据集
ds = Dataset.from_dict({
    "question": questions,
    "answer": answers,
    "contexts": contexts_list,
    "ground_truth": ground_truths
})

# 4. 执行评估
result = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision])
print(result)
result.to_pandas().to_csv("ragas_report.csv", index=False, encoding="utf-8")
print("报告已保存到 ragas_report.csv")
```

**预期输出**：终端打印三个指标的平均分，类似：

```
{'faithfulness': 0.72, 'answer_relevancy': 0.68, 'context_precision': 0.55}
```

这些分数的含义：忠实度 0.72 意味着约 72% 的答案断言有上下文支撑，剩余 28% 可能是幻觉；相关性 0.68 表示回答约有三分之一内容没有直接回应问题；精准度 0.55 说明检索到的上下文中近一半是噪音。

**这是你的基线（Baseline）**。记下这三个数字——经过 9.4 节维护后再跑一次，对比提升。

**练习：检验评估集的敏感性**

`ground_truth` 字段在 RAGAS 中用于计算答案相关性（通过比较生成答案与标准答案的语义相似度），但有时它并不是精确的“标准答案”，而更接近一个参考摘要。为了理解它的影响，请手动打开 `eval_dataset.json`，选择 3 条记录，将其 `answer` 字段改写为明显错误的事实（比如把“读已提交”的解释改成“串行化”的定义），然后重新运行 `run_ragas.py`。观察答案相关性分数是否下降，忠实度是否受影响。这个实验会告诉你：如果自动生成的 ground_truth 本身质量不高，相关性分数的指向就会偏差，因为 RAGAS 把生成答案与可能不准确的 ground_truth 进行比较。因此，**评估集本身也需要质量校验**。理想情况下，应该随机抽查 10% 的自动生成问答对，人工确认其正确性后再纳入评估。

**边界：评估集太小或太偏**

如果你的知识库只有 15 篇笔记，且都集中在“分布式系统”一个主题，生成的 20 个问题可能会高度同质化。RAGAS 报告的平均分可能看起来很漂亮，但一旦遇到一个超出范围的问题，系统表现就会骤降。这是评估集覆盖度不足导致的“实验室高分”。弥补方法：在运行评估前，人工确认问题覆盖了知识库中至少 3 个不同的主题标签；若不足，可以手动补充几条跨领域问题，并自己写出 ground_truth。

**边界：评估指标在本地小模型上的稳定性差异**

RAGAS 默认使用 LLM 充当评估法官——即让一个模型去评判另一个模型生成的答案。在你的本地环境中，这个“法官”就是你本机的 `qwen2.5:7b`。7B 模型在评估一致性（如“第二段是否忠实于上下文”）上的判断力不如云端大模型稳定。如果你发现两次运行相同评估集得到的分数波动超过 0.1，这说明本地法官有随机性。此时，可信的做法是：抽取 5 条评估用例，人工对照上下文和答案逐条打分，并与 RAGAS 给出的分数对比。如果人工分数与 RAGAS 分数在 0.15 以内，本地法官基本可信；否则，你应该更多依赖人工抽检，而非单纯盯着 RAGAS 数字。

---

## 9.4 切片二：知识库健康诊断与防退化

### 9.4.1 三种常见的知识库腐化

回顾 9.3 的评估结果：如果上下文精准度低，说明向量检索在大量返回不相关内容。原因通常在三个方向：

**向量漂移（Vector Drift）**：当你反复更新一篇笔记，旧的 embedding 还在向量库中，新内容却对应了不同的向量表示。检索时新旧并行，返回互相矛盾或过时的上下文。

**冗余积压**：你新建一篇笔记时，可能把原笔记内容复制了一份。两个语义高度重叠的片段都进入向量库，检索时它们瓜分权重，挤占真正多样化的结果。

**碎片化笔记**：一篇笔记覆盖了三个不相关的主题，被切分成多个块后，每个块都携带了混合信号。当检索某个主题时，包含另一主题的块也被召回——噪音。

可观察示例：验证向量漂移

为了让你直观感受“漂移”，可以进行一个微实验。取一篇你经常修改的笔记，比如《分布式系统学习路线》。把它的当前内容复制到剪贴板，然后调用嵌入 API：

```python
import requests, json
text_v1 = "第一版内容：重点学习 Raft 和 Paxos。"
resp = requests.post("http://localhost:11434/api/embed", json={"model":"nomic-embed-text","input":text_v1})
emb_v1 = resp.json()["embeddings"][0]

# 模拟修改后的第二版
text_v2 = "更新后的路线：深入 Raft，Paxos 作为历史了解，新增 Byzantine Fault Tolerance。"
resp = requests.post("http://localhost:11434/api/embed", json={"model":"nomic-embed-text","input":text_v2})
emb_v2 = resp.json()["embeddings"][0]

# 计算余弦相似度
dot = sum(a*b for a,b in zip(emb_v1, emb_v2))
norm1 = (sum(a*a for a in emb_v1))**0.5
norm2 = (sum(b*b for b in emb_v2))**0.5
sim = dot / (norm1 * norm2)
print(f"版本间余弦相似度: {sim:.4f}")
```

如果相似度低于 0.85，而向量库中仍存着 v1 的嵌入，那么当用户查询“Raft 与 Paxos 的关系”时，v1 和 v2 可能都被召回，但 v1 提供的上下文是过时的“重点学习”，与 v2 的“历史了解”产生矛盾。这就是漂移的微观机制。当篇数增多，这种矛盾片段会在检索结果中累积，导致上下文精准度下降。

### 9.4.2 维护脚本：检测冗余和孤立笔记

创建 `maintenance/diagnose.py`：

```python
import os, json, hashlib
from pathlib import Path
from collections import defaultdict
import requests

VAULT = os.path.expanduser("~/Documents/Obsidian/Vault")
OLLAMA_EMBED = "http://localhost:11434/api/embed"
SIMILARITY_THRESHOLD = 0.85

def get_embedding(text: str) -> list:
    resp = requests.post(OLLAMA_EMBED, json={
        "model": "nomic-embed-text", "input": text[:2000]
    })
    return resp.json()["embeddings"][0]

def cosine_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = sum(x*x for x in a)**0.5
    norm_b = sum(x*x for x in b)**0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0

# 1. 扫描所有笔记
notes = []
for root, dirs, files in os.walk(VAULT):
    dirs[:] = [d for d in dirs if d not in ('.obsidian', '.trash')]
    for f in files:
        if f.endswith(".md"):
            path = Path(root) / f
            content = path.read_text(encoding="utf-8")
            notes.append({
                "path": str(path), "filename": f,
                "content": content, "size": len(content)
            })

print(f"扫描到 {len(notes)} 篇笔记")

# 2. 检测冗余对（内容高度相似）
similar_pairs = []
embeddings = {}
for note in notes:
    emb = get_embedding(note["content"])
    embeddings[note["path"]] = emb

checked = set()
for n1 in notes:
    for n2 in notes:
        if n1["path"] == n2["path"]: continue
        pair_key = tuple(sorted([n1["path"], n2["path"]]))
        if pair_key in checked: continue
        checked.add(pair_key)
        sim = cosine_sim(embeddings[n1["path"]], embeddings[n2["path"]])
        if sim > SIMILARITY_THRESHOLD:
            similar_pairs.append({"note_a": n1["filename"], "note_b": n2["filename"], "similarity": round(sim, 3)})

print(f"\n发现 {len(similar_pairs)} 对高度相似笔记：")
for p in similar_pairs:
    print(f"  {p['note_a']} ↔ {p['note_b']} (相似度 {p['similarity']})")

# 3. 检测孤立笔记（无双链、无反向链接的笔记）
# 简化版：检查内容中是否包含 [[
isolated = []
for note in notes:
    has_wikilink = "[[" in note["content"]
    if not has_wikilink:
        isolated.append(note["filename"])

print(f"\n发现 {len(isolated)} 篇无 [[双链]] 的孤立笔记：")
for f in isolated:
    print(f"  {f}")
```

运行并观察：
```bash
python maintenance/diagnose.py
```

预期输出解读：
- 相似度 > 0.85 的笔记对意味着你很可能在不同时间记录了相同内容，应合并或删除其中一篇
- 孤立笔记不一定需要删除（有些笔记本身就是独立概念），但它是图谱中的“孤岛”，AI 无法通过双链跳转发现它

处理动作（需手动确认）：
1. 对高相似笔记对，检查内容，保留更完整的一篇，在另一篇中添加 `aliases:` 指向保留笔记，并移动至 `.archive` 目录
2. 对孤立笔记，判断是否应该添加至少一条双链，或者在 Frontmatter 标记 `status: reference`（表示独立参考资料）

**练习：调节阈值理解精度与召回**

`SIMILARITY_THRESHOLD` 决定了脚本会将多相似的笔记对视为“冗余”。试着将它从 0.85 逐渐降低到 0.75，再提高到 0.95，每次运行 `diagnose.py` 并记录发现的冗余对数量。你会发现，较低的阈值会捕捉到更多“可能相似”的笔记（高召回），但其中包含更多只是同一主题但不同角度的笔记（低精度）。较高的阈值则只标记几乎完全相同的笔记，可能漏掉那些换了表述但核心内容重复的笔记。你的任务不是找到一个“魔法数字”，而是理解：**维护脚本的阈值必须根据知识库的主题聚合度手工校准**。一个策略是：先用 0.85 跑一次，对结果做人工确认后，将确认的冗余对作为标准，反推一个使精度和召回平衡的阈值。

### 对嵌入 API 的速率限制保持警惕

`diagnose.py` 会为每篇笔记调用一次 `/api/embed`，在笔记数量超过 50 篇时，连续无间隔请求可能触发 Ollama 的内置排队或超时。如果你的知识库较大，可在 `for note in notes:` 循环中加入 `time.sleep(0.5)`，并观察 Ollama 服务日志（通常位于 `~/.ollama/logs/server.log`）确认无 429 或超时错误。此限制同样适用于 `sync_vector.py` 的重建索引操作，忽略它会导致部分笔记嵌入丢失，而脚本不会报错。

### 9.4.3 增量重索引：解决向量漂移

维护脚本只诊断不治疗。真正的“治疗”是让向量库与 Markdown 源文件重新对齐：

```bash
# 方案：删除旧索引并根据现有文件全量重建
python sync_vector.py --full-reindex
```

这条命令是第 8 章 `sync_vector.py` 的扩展调用（请在同步脚本中添加 `--full-reindex` 标志，逻辑为：清空 LanceDB 表，重新遍历 VAULT 目录执行 embed + insert）。重建后再次运行 9.3.3 的 `run_ragas.py`，观察精准度变化。

**可观察判据**：精准度提升超过 0.1 则说明原向量库存在严重漂移。

**边界：全量重建的潜在陷阱**

在笔记数量超过 200 篇时，`--full-reindex` 会依次对每篇笔记调用嵌入 API。这不仅耗时，还可能触发 Ollama 的并发限制（如果未来你并行化了该脚本）。更隐蔽的问题：如果重建过程中你有新笔记写入，或者某篇 .md 文件在读取时被其他进程短暂锁定，部分笔记可能被跳过而没有报错，导致索引不完整。**防御措施**：重建前，先确保 Obsidian 已完全关闭（或至少没有正在编辑的笔记），重建完成后立即用 `ls -l` 核对 LanceDB 表中的记录数与 Vault 中的 .md 文件数相差不超过 2（允许 Frontmatter 空白行差异）。如果你的知识库已经很大，可以考虑先按目录分区重建，而非一次性全量操作。

---

## 9.5 切片三：Agentic 闭环——让知识库自己写笔记

### 9.5.1 闭环设计

一条完整的 Agentic 流水线有四个阶段，每个阶段都对应明确的输入输出和验证点：

```
[用户提问] → ①检索 → ②生成草稿 → ③结构化解析 → ④写回Obsidian
                  ↑                                                  |
                  └────────── 更新索引 ← 新笔记 ← 写回双链/Tag ←──────┘
```

**阶段职责**：

| 阶段 | 输入 | 输出 | 负责组件 |
|------|------|------|----------|
| ①检索 | 用户课题（如“分布式系统共识算法的演进”） | Top-5 笔记片段 + 图谱邻居节点 | LanceDB + MCP search_notes |
| ②生成 | 检索上下文 + 课题 | Markdown 格式的结构化草稿（含标题、正文、参考笔记的双链） | Ollama LLM |
| ③解析 | LLM 生成的 Markdown 字符串 | 结构化字段：标题、正文、tags、references（要链接的笔记名列表） | Python 正则 + Frontmatter 解析 |
| ④写回 | 解析后的结构化字段 | 新的 `.md` 文件，包含 YAML Frontmatter、正文、双链 | Python 文件写入 |

**设计决策：为什么不使用 LangChain Agent**

你可能注意到我们直接编写了函数式流水线，而未使用 LangChain 的 Agent 框架。这是刻意选择：Agent 框架的优势在于工具调用和推理循环，但这个闭环的主要操作——检索、生成、解析、写文件——都是确定性的步骤，不需要 LLM 在运行时决定调用哪个工具。用简单的函数串联，每步的输入输出都可以轻易打印和调试；而引入 Agent 循环会引入额外的延迟和不确定性（例如 LLM 可能错误地选择不调用搜索工具）。当你的闭环未来需要动态决策（例如“如果检索结果不足，自动调整查询词重试”），那时再考虑引入 Agent 模式会更有效。

**写回的安全边界设计**

第 8 章的 MCP Server 是只读的，这是有意为之——暴露写入能力而未加控制，意味着外部工具可以删除你的笔记。本章的 `write_note` 步骤在打破只读限制的同时，施加了严格的安全约束：写入路径硬编码为 `VAULT/Research/` 子目录，绝不触碰 vault 其他位置。这意味着 Agent 创建的所有笔记都集中在 `Research/` 下，即便发生误写或覆盖，你的手工笔记仍然安全。同时，每条自动生成的笔记都标记了 `auto_generated: true`，方便你后续按 Frontmatter 字段批量过滤和审核。

可观察示例：在终端中跟踪一次闭环的完整信号流

在运行 `research_agent.py` 时，观察控制台打印的每一步结果。一次典型的执行会显示：`[1/4]` 输出 5 篇笔记的文件名，其中第一和第三篇直接相关，第二篇仅在“分布式系统”词面上相似但内容偏存储；`[2/4]` 生成的 Markdown 草稿第一段引用了第一篇笔记的双链；`[3/4]` 标签列表中包含“共识算法”“Paxos”“Raft”；`[4/4]` 文件路径明显指向 Research 子目录。如果第二步的草稿中出现 `[[分布式文件系统]]` 这样的无关双链，说明检索返回的第二篇笔记噪声被模型采用了。此时你可以回到 9.4.3 考虑重建索引，或者在 `generate_draft` 的提示中增加“仅引用与主题直接相关的笔记”来强化指令。

### 9.5.2 构建 Agent 主脚本

创建 `agent/research_agent.py`：

```python
import os, json, re, yaml
from pathlib import Path
from datetime import datetime
import requests
import lancedb

VAULT = os.path.expanduser("~/Documents/Obsidian/Vault")
LANCE_DIR = os.path.expanduser("~/obsidian-rag-data/lancedb")
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_EMBED = "http://localhost:11434/api/embed"
MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"

def search_notes(query: str, top_k: int = 5) -> list:
    """直接用 LanceDB 原生检索，返回笔记片段列表"""
    db = lancedb.connect(LANCE_DIR)
    table = db.open_table("notes")
    resp = requests.post(OLLAMA_EMBED, json={"model": EMBED_MODEL, "input": query})
    q_emb = resp.json()["embeddings"][0]
    results = table.search(q_emb).limit(top_k).to_list()
    return [{"filename": r["filename"], "content": r["content"], "path": r["path"]} for r in results]

def generate_draft(topic: str, contexts: list) -> str:
    ctx_text = "\n\n---\n\n".join([f"来源：[[{c['filename'].replace('.md','')}]]\n{c['content'][:800]}" for c in contexts])
    prompt = f"""你是知识库的自动研究助手。用户提出课题，你需要综合以下笔记上下文，生成一篇结构化的知识库笔记草稿。

要求：
1. 用一级标题 `# 课题名`
2. 正文分节使用 `## 小节标题`
3. 在正文中自然引用相关笔记，使用 Obsidian 双链语法 `[[笔记名]]`
4. 结尾列出 `## 参考` 小节，用列表列出所有参考笔记的双链
5. 返回纯 Markdown，不要额外解释

课题：{topic}

上下文（共 {len(contexts)} 篇相关笔记）：
{ctx_text}"""
    
    resp = requests.post(OLLAMA_URL, json={
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.7, "num_predict": 2000}
    })
    return resp.json()["response"].strip()

def parse_draft(markdown: str) -> dict:
    """解析 LLM 生成的草稿，提取元数据"""
    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "未命名课题"
    
    # 提取所有 [[双链]]
    wikilinks = re.findall(r"\[\[([^\]]+)\]\]", markdown)
    # 去重
    unique_refs = list(dict.fromkeys(wikilinks))
    
    # 尝试提取已有的 tags（如果 LLM 生成了）
    tag_match = re.search(r"tags:\s*\[([^\]]*)\]", markdown)
    existing_tags = [t.strip() for t in tag_match.group(1).split(",")] if tag_match else []
    
    # 自动根据课题关键词生成 tags
    auto_tags = [w.lower() for w in re.findall(r"[\u4e00-\u9fff\w]+", title) if len(w) > 2][:3]
    all_tags = list(set(existing_tags + auto_tags))
    
    return {
        "title": title,
        "content": markdown,
        "references": unique_refs,
        "tags": all_tags
    }

def write_note(parsed: dict) -> str:
    """在 Obsidian Vault 中创建新笔记"""
    # 安全文件名
    safe_name = re.sub(r'[\\/:*?"<>|]', '-', parsed["title"])
    note_path = Path(VAULT) / "Research" / f"{safe_name}.md"
    note_path.parent.mkdir(exist_ok=True)
    
    # 文件名冲突检查：若已存在则追加时间戳
    if note_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        note_path = note_path.with_stem(f"{safe_name}-{timestamp}")
    
    # 构建带 Frontmatter 的笔记
    frontmatter = {
        "title": parsed["title"],
        "tags": parsed["tags"],
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type": "research-note",
        "auto_generated": True
    }
    
    full_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{parsed['content']}"
    note_path.write_text(full_content, encoding="utf-8")
    return str(note_path)

def agentic_research(topic: str):
    """主闭环流程"""
    print(f"[1/4] 检索相关笔记...")
    contexts = search_notes(topic)
    print(f"  找到 {len(contexts)} 篇相关笔记")
    for c in contexts:
        print(f"    - {c['filename']}")
    
    print(f"[2/4] 生成研究草稿...")
    draft = generate_draft(topic, contexts)
    print(f"  草稿长度: {len(draft)} 字符")
    
    print(f"[3/4] 解析草稿结构...")
    parsed = parse_draft(draft)
    print(f"  标题: {parsed['title']}")
    print(f"  标签: {parsed['tags']}")
    print(f"  引用笔记: {parsed['references']}")
    
    print(f"[4/4] 写入 Obsidian...")
    path = write_note(parsed)
    print(f"  新笔记已创建: {path}")
    
    return parsed

if __name__ == "__main__":
    topic = input("请输入研究课题: ").strip()
    if topic:
        agentic_research(topic)
```

**处理超长笔记生成时的嵌入分块**

当 Agent 生成的草稿超过 2000 字时，全文嵌入可能超出 `nomic-embed-text` 模型的上下文窗口（虽然该模型支持较长输入，但质量会随文本增长而衰减）。后续运行 `sync_vector.py` 同步新笔记时，如果同步脚本仍使用段落切分（按 `\n\n` 分割），长草稿会被自动切割为多个块，每块独立获得嵌入，对检索质量没有负面影响。但如果你需要将整篇草稿作为一句话嵌入（例如用于笔记间相似度计算），建议对超过 500 字的文本先提取摘要再嵌入，而非直接对整个文本向量化。这是向量检索的普遍限制：整篇嵌入会稀释核心语义，并非 Agent 独有的问题。

### 9.5.3 首次运行与验证

确保 Ollama 和 LanceDB 都在运行状态后：

```bash
python agent/research_agent.py
```

输入课题：`分布式系统共识算法的演进`

**观察四步输出**：
1. `[1/4]` 应列出 5 篇相关笔记名——如果全是无关笔记，回到 9.4.3 重建索引
2. `[2/4]` 草稿长度应 > 1000 字符——不足则模型可能 token 限制过低，调整 `num_predict`
3. `[3/4]` 应提取到 3 个以上 `tags` 和至少 2 个 `[[双链]]`
4. `[4/4]` 路径应指向 `~/Documents/Obsidian/Vault/Research/` 下的新 `.md` 文件

**在 Obsidian 中验证**：
- 打开 Obsidian，确认新笔记出现在文件列表
- 切换到图谱视图（Ctrl+G），观察新节点是否连接到引用的笔记
- 打开新笔记，检查 Frontmatter 的 `tags` 和正文中的 `[[双链]]` 是否可点击

**边界与失败模式**

Agent 可能遇到几种常见失效，需要提前防范：

- **检索结果为空**：如果课题与知识库完全无关（如“古罗马引水渠”），`search_notes` 仍会返回余弦相似度最高的 5 条记录，但这些内容几乎不相关。生成的草稿可能凭空编造，或直接复制不相关笔记的段落并强行附会。**应对**：你已在 `generate_draft` 的提示中要求“如果上下文信息不足，请说明”，但 7B 模型并不总是遵守。更可靠的方案是在解析阶段检查 `references` 的数量：如果引用的笔记数量为 0，则在 Frontmatter 中添加 `quality: low` 标记，提醒自己后续人工审核。

- **LLM 输出非 Markdown**：有时模型会返回带前言或结语的文字，而不是纯 Markdown。`parse_draft` 用正则提取标题和双链，但可能遗漏格式混乱的情况。如果 `title` 是“未命名课题”，说明解析失败，应打印草稿全文并手动检查。

- **文件名冲突**：如果 `写回` 步骤发现目标路径已存在同名文件，当前实现会在文件名后追加时间戳，而非覆盖已有笔记。这意味着你不会丢失之前的笔记，但可能在 `Research/` 目录下产生同一课题的多个版本。你应当定期检查该目录，合并或归档旧版本。

- **本地模型幻觉加剧**：7B 模型在生成长草稿时容易在中间段落开始重复短语或编造引用。如果你发现 `references` 列表中包含知识库中不存在的笔记名（例如模型自己编了一个 `[[某虚构论文]]`），你需要增加后处理：检查每个 `reference` 对应的 .md 文件是否存在，删除无效引用。

**练习：极端输入测试**

尝试输入一个极短的课题，比如“AI”，然后观察草稿的质量。随后输入一个非常具体但本地知识库不太可能覆盖的课题，如“F1 赛车空气动力学”。比较两次检索返回的上下文内容、草稿的相关性和引用的有效性。这个练习的价值在于让你感受：Agent 的表现高度依赖检索质量，而检索质量又依赖于知识库的覆盖度。当知识库在某领域薄弱时，Agent 并不会“承认无知”，而是会尽力拼凑——这是当前技术的边界。

### 9.5.4 迭代改进：第二种闭环模式

以上是可手动触发的“拉取式”闭环。你还可以配置 **定时自动巡检**——每天凌晨让 Agent 扫描最近修改的笔记，发现孤立笔记后自动生成“建议链接”并写入一条待办。

在 `agent/` 下创建 `auto_curator.py`（核心逻辑片段）：

```python
# 伪代码结构
def daily_curation():
    recent_notes = scan_recently_modified(hours=24)
    for note in recent_notes:
        if is_isolated(note):  # 无双链
            related = search_notes(extract_keywords(note))
            suggestions = [f"[[{r['filename'].replace('.md','')}]]" for r in related[:3]]
            # 在笔记底部追加待办
            append_to_note(note, f"\n\n> [!todo] 建议链接\n> {', '.join(suggestions)}")
```

这个模式的停止条件：所有最近修改的笔记都至少包含一条双链或明确的“无需链接”标记（如 Frontmatter `link_status: standalone`）。本章不展开完整实现，但你应该能基于 9.5.2 的组件拼接出来。

---

## 9.6 项目收束：验收、复盘与独立挑战

### 9.6.1 完整验收清单

按顺序执行以下检查，每项通过后打勾：

- [ ] **评估基线**：`ragas_report.csv` 存在且包含 ≥ 20 行的 faithfulness / answer_relevancy / context_precision 分数
- [ ] **维护诊断**：`diagnosis.py` 运行后输出了相似笔记对和孤立笔记列表
- [ ] **重建索引**：全量 reindex 后，上下文精准度比基线提升 > 0.05
- [ ] **闭环运行**：输入任意课题后，Obsidian 中生成新笔记，包含可点击双链和 Frontmatter tags
- [ ] **图谱连通性**：新节点在 Obsidian 图谱中至少连接到一个已有节点
- [ ] **错误处理**：故意输入一个与知识库完全不相关的课题（如“古罗马水道工程”），Agent 应生成草稿但明确标记 `auto_generated: true` 并在正文说明“知识库中未找到相关笔记”

### 9.6.2 独立任务：故障修复

你不需要逐行指令。这里给出一个预设的故障场景：

**场景**：你运行 `research_agent.py` 两周后，发现新生成的笔记质量下降——生成的草稿开始重复使用同一篇笔记作为唯一来源，其他 4 个检索结果被忽略。同时，向量检索日志显示 `search_notes` 返回的 Top-5 中有 3 条是高度相似的冗余笔记。

**你的任务**：
1. 诊断问题根因（提示：回顾 9.4.1 的三种腐化类型）
2. 提出修复方案
3. 实施修复，重新运行 Agent，比较修复前后的草稿引用多样性

**验收标准**：修复后生成的草稿至少引用 2 篇不同的源笔记。

**练习：撰写诊断报告**

完成上述修复后，请写一段 200-300 字的诊断报告，记录以下三件事：（1）你是通过什么观察（日志、分数、文件内容）定位到根因的；（2）你采取了什么具体修复动作（删除冗余、重建索引、手动合并笔记等）；（3）修复后的证据是什么（比如 `ragas_report.csv` 中精准度从 0.55 提升到 0.68，或草稿中不同引用数由 1 变为 3）。这份报告就是你自己知识库的健康档案，下次遇到类似退化时，它能帮你更快定位。

### 9.6.3 课程总结：你建成的是什么

从第 1 章到第 9 章，你不只是在学工具。你建造的是一套分层的知识工程系统：

```
应用层：Obsidian 笔记界面 + 3D 图谱可视化
     ↓
集成层：MCP Server → Cursor / Claude Code
     ↓
智能层：RAGAS 评估 → Agentic 闭环
     ↓
检索层：混合检索(BM25+向量) + GraphRAG 多跳推理
     ↓
存储层：Markdown 源文件 + LanceDB 向量索引 + Ollama 本地推理
```

这套系统的每一次运行都会产生可观测的证据——分数、文件、图谱节点。你可以用 RAGAS 分数驱动优化，而非凭感觉判断。

**三条后续进化方向**（本章不实现，但你应该知道可以往哪走）：
1. **多模态**：让 Agent 能检索图片和 PDF，结合 OCR 和视觉模型
2. **协作过滤**：如果你和其他人共享知识库，引入协同过滤推荐“别人在你当前笔记下常读的下一篇”
3. **微调闭环**：收集 Agent 生成草稿后你的修改记录，作为偏好数据微调本地模型，让未来的草稿更贴合你的写作风格

---

## 9.7 常见问题与恢复

| 症状 | 可能原因 | 恢复方式 |
|------|----------|----------|
| `search_notes` 返回空结果 | LanceDB 表不存在或路径错误 | 运行 `sync_vector.py --full-reindex` |
| 草稿生成超时 | Ollama 模型过大或 `num_predict` 过高 | 调低 `num_predict` 至 1500，或换用 `qwen2.5:3b` |
| 新笔记 Frontmatter 乱码 | LLM 输出的 YAML 不符合规范 | 在 `parse_draft` 中增加 YAML 校验，失败时使用默认值 |
| 评估分数始终低于 0.5 | 知识库笔记数量或质量不足 | 优先增加 10 篇以上原子化笔记（回顾第 2 章） |
| Agent 创建了重复笔记 | 已有同名笔记但未检查 | `write_note` 已内置冲突检测，自动追加时间戳 |

---

Agentic 闭环让知识库能自动诊断和生成笔记。一开始效果可能不够理想，但反复运行诊断和重建索引会持续改进——迭代比一次搭建重要得多。

---

## 参考文献
- RAGAS: Evaluation framework for RAG systems. [https://docs.ragas.io/](https://docs.ragas.io/) — 支撑 9.3 节的评估维度定义和 API 调用方式
- Ollama API Documentation: OpenAI Compatibility. [https://docs.ollama.com/api/openai-compatibility](https://docs.ollama.com/api/openai-compatibility) — 支撑 9.3-9.5 节点的本地模型调用
- LanceDB Python API. [https://lancedb.github.io/lancedb/](https://lancedb.github.io/lancedb/) — 支撑向量检索的 `search()` 方法调用
- Obsidian Developer Documentation: Vault API. [https://docs.obsidian.md/](https://docs.obsidian.md/) — 支撑 Markdown 文件操作和双链语法的正确性
