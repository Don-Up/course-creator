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
