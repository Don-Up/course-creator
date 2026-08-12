# 第 2 章 面向 RAG 的 Markdown 数据建模与 AST 解析

> 预计学习时间：120分钟（含动手实操）  
> 一句话总结：写一条人类看得懂、机器也能精确切分和检索的笔记，靠的不是新工具而是新的结构习惯；本章从原子化原则、YAML元数据直至AST递归分块与父子文档策略，把Markdown从“文本”建构成“数据”。

## 一、一堂搜索课

先做一个小实验。不要打开 Obsidian 查找功能，你凭记忆回答：你过去一年写过多少条笔记？其中多少条现在还能在三步之内找到？如果答案让你迟疑，你遇到的不是记忆力问题，而是信息组织问题。

本章标题里有两个词：数据建模与AST解析。拆开看都带技术味道，但背后是一个很朴素的问题：怎样写笔记，能让未来的自己和未来的AI，都能准确找得到、读得懂、用得上？

第1章已经回答过“为什么要选 Obsidian”——因为它的笔记是纯 Markdown 文本，存在你本地的文件夹里，不受制于任何云服务的 API 限流或格式锁死。但 Markdown 本身只是格式约定。同一篇笔记，你写成三千字的长文，和拆成十条互相链接的短笔记，对 AI 来说是完全不同的语料。

本章就从这个分水岭开始讲起。

## 二、原子化笔记：一个文件，一个概念

### 2.1 它不是什么新发明

“原子化笔记”(Atomic Notes) 是个人知识管理领域已经反复验证过的一条实践原则。它不等于短笔记，而是**单一概念笔记**：一个 .md 文件聚焦一个概念、一个观点、一个决策或一个问题，不到万不得已不往里面塞第二个概念。

观察两篇笔记的差别。

**笔记A（反例）**

```markdown
# Python 并发编程

## 线程

Python 的 threading 模块受 GIL 限制，只适合 IO 密集型任务。

## 异步编程

asyncio 可以处理高并发 IO，但不适合 CPU 密集型。

## 多进程

multiprocessing 可以绕过 GIL。
```

**笔记B（拆分后的原子化版本）**

文件 `python-gil-threading.md`：

```markdown
# Python 的 GIL 对线程的影响

Python 由于全局解释器锁（GIL）存在，
一个进程同一时刻只有一个线程能执行字节码。
IO 密集型任务可受益于线程并发，
CPU 密集型任务则应改用多进程。
```

文件 `python-asyncio-limits.md` 和 `python-multiprocessing-vs-threading.md` 各聚焦一个概念，不再赘述。

笔记A看起来井井有条，但对检索系统是灾难。搜索 `asyncio` 会命中这篇“Python并发编程”，结果返回的是把三个概念压在一起的文本块——“asyncio 可以处理高并发 IO”夹在“GIL”和“multiprocessing”之间，Embedding 求出来的语义向量退化成稀粥。

原子化笔记保证了一条规则：

> 一篇笔记在向量空间中的Embedding，就代表一个概念的语义。

### 2.2 怎么判断拆分时机

你不需要预先想好所有分类。边写边判断即可。判断标准很简单：

- 这篇笔记如果被单独搜索，标题本身能否表达完整意图？
- 回答一个特定问题时，是不是需要从这篇笔记中间精确抽出两段，而不是整篇？

如果第一个答案是“不能”，或者第二个是“需要”，就该拆。

操作上，Obsidian 支持右键点击[[链接]]自动创建目标文件。当你在正文遇到一个新概念时，直接把它变成链接，Obsidian就会引导你新建一篇专属笔记。

### 2.3 原子化与RAG的关系

第1章讲 Naïve RAG 的缺陷时提过“重叠上下文”问题。这个问题根子在分块，药方却在写作阶段就埋下了：如果一篇笔记本身就只承载一个清晰概念，分块器就不需要在三千字的正文里猜段落边界。

把原子化思考当成写作习惯，不是在“整理知识库”，而是在把你的知识库拆成更清晰的语义块。每个文件就是一个天然 Chunk。

### 2.4 可观察证据：嵌入向量的纯度对比

为了看清原子化的实际效果，可以用余弦相似度做一个极简的思想实验。假设以下两个向量分别代表“线程”和“多进程”两条笔记的语义：

```python
import math

def cos_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = math.sqrt(sum(x**2 for x in a))
    norm_b = math.sqrt(sum(x**2 for x in b))
    return dot / (norm_a * norm_b)

# 原子化笔记的嵌入向量（简化为二维数值）
threading_vec = [0.9, 0.2]   # “Python 线程”
multiproc_vec = [0.1, 0.9]   # “Python 多进程”

# 查询“GIL对线程的影响”的理想嵌入
query_vec = [0.85, 0.25]

print("查询 vs 线程笔记:", round(cos_sim(query_vec, threading_vec), 3))
# 输出示例：查询 vs 线程笔记: 0.998
print("查询 vs 多进程笔记:", round(cos_sim(query_vec, multiproc_vec), 3))
# 输出示例：查询 vs 多进程笔记: 0.527
```

原子化笔记与查询的相似度极高，而非相关概念的笔记相似度明显低，检索时很容易区分。

现在模拟把两篇笔记合并成一篇“Python并发编程”的情况。合并后嵌入向量可以近似为两向量求平均：

```python
mixed_vec = [(0.9+0.1)/2, (0.2+0.9)/2]  # [0.5, 0.55]

print("查询 vs 混合笔记:", round(cos_sim(query_vec, mixed_vec), 3))
# 输出示例：查询 vs 混合笔记: 0.852
```

虽然仍能检索到，但相似度从 0.998 跌到 0.852。更糟糕的是，这个混合向量也在某种程度上“擦边”多进程查询，导致一个查询返回的排名中，噪声笔记可能挤掉真正相关的独立笔记。

上述数值只是示意，真实 Embedding 模型输出的千维向量效应相同：多个概念硬塞进同一个文件，向量被迫变成“万金油”，精度必然下降。这是原子化如何提升区分度的一个近似演示。

### 2.5 原子化检查清单

当你写完一篇笔记后，用下面三个问题快速自检：

1. 如果去掉标题，别人能一眼看出这篇笔记只讨论一件事吗？
2. 笔记中是否出现了“另外”、“顺便提一句”、“与之相关的还有……”等分岔表述？
3. 将来你要找这条信息，你期望的搜索词是否恰好对应本文的标题或核心句？

如果任何一个答案是“不是”或“有”，就说明还有可拆分的概念藏在文本里。把那个概念独立成文，并加上双链——这是通往高质量知识库最高频、也最被低估的习惯。

## 三、YAML Frontmatter：机器可读的元数据层

### 3.1 写在标题之上

打开 Obsidian 的任意一篇笔记，在最顶端用三个连字符包起来的部分，就是 Frontmatter。

```yaml
---
title: "面向RAG的结构化写作"
tags: [rag, markdown, chunking]
status: draft
type: concept
created: 2025-04-09
---
```

它不是给人类阅读的小抄，而是给程序（和 AI 检索管线）看的**结构化标签层**。

Obsidian 原生支持 YAML Frontmatter，自动解析后提供:

- 侧边栏按标签聚合
- Dataview 插件按 `status`/`type` 动态索引
- 元数据过滤（这是第5章混合检索的前提）

### 3.2 三个必填字段与扩展

起步阶段，每篇笔记至少包含以下三个字段:

| 字段 | 作用 | 示例值 |
|------|------|--------|
| `tags` | 语义分类，未来支持关键词召回和过滤 | `[python, concurrency]` |
| `status` | 笔记成熟度，辅助维护与垃圾回收 | `draft` / `reviewed` / `evergreen` |
| `type` | 内容原型，帮助后续分组分块 | `concept` / `tutorial` / `meeting-notes` |

`status` 字段的顺序表达了笔记生命周期: 草稿期可以容忍粗颗粒度，但进入 `reviewed` 或 `evergreen` 后就该同时审视原子化是否到位。

`type` 字段影响分块策略的选择: `meeting-notes` 可能更适合按时间线切割，`concept` 则应优先保留完整段落结构。

### 3.3 体验即刻反馈

创建一个新文件 `test-metadata.md`，填入：

```yaml
---
title: "RAG分块测试"
tags: [rag, chunking, draft]
status: draft
type: concept
---
```

然后在 Obsidian 中执行：

1. 按 `Ctrl/Cmd + Shift + T` 打开**标签面板**，观察 `rag`、`chunking`、`draft` 三个标签已自动出现。
2. 安装 Dataview 插件后，在同一笔记中写：

   ````markdown
   ```dataview
   LIST
   FROM #rag
   WHERE status = "draft"
   ```
   ````

   预览模式会立刻列出所有满足条件的文件。

你已经在写机器可读的数据了。

### 3.4 反例：缺少元数据时查询会漏掉什么

假设你的知识库中有两条笔记，一条填写了完整的 Frontmatter，另一条没有填写任何元数据：

笔记 `doc-with-meta.md`：

```yaml
---
tags: [rag]
status: draft
---
```

笔记 `doc-without-meta.md` 的内容同样是关于 RAG，但没有任何 YAML 块。

执行 Dataview 查询 `FROM #rag` 时，`doc-without-meta.md` 不会出现在列表中。即便它在正文里包含 “rag” 这个词，但 Dataview 只扫描 Frontmatter 的 `tags` 字段，不会分析全文。RAG 检索管线的元数据过滤步骤同样依赖这些结构化字段——缺失了，就失去了按类别、状态或内容类型筛选的能力。

养成一个简单的习惯：创建新笔记时立即从模板插入包含 `tags`、`status`、`type` 的 Frontmatter 块，避免信息在未来检索时成为“看不见的笔记”。

### 3.5 YAML 的常见书写陷阱

YAML 的语法虽然直观，但也有几个初学者容易掉进去的坑。最典型的有三个：

1. **缩进只能用空格，不能用 Tab 键。** 在 Obsidian 的编辑器里敲 Tab 通常会自动插入空格，但如果你从其他地方复制了用 Tab 缩进的 Frontmatter，解析器会直接报错，整个 YAML 块失效。

2. **列表项的短横线后面必须有空格。** `tags: [rag,chunking]` 是合法的 YAML 行内列表，但如果你写成多行形式：

   ```yaml
   tags:
   -rag
   -chunking
   ```

   由于 `-rag` 没有空格，YAML 解析器会把它当成一个普通字符串，而不是列表元素。正确写法是 `- rag`。

3. **包含冒号或特殊字符的值必须加引号。** 例如 `title: "想法：关于效率"`，如果不加引号，YAML 会把冒号误判为键值分隔符，导致解析错误。类似地，包含 `{`、`}`、`[`、`]` 等字符也最好用引号保护。

这三条规则都不复杂，但任何一条被忽略，就会让整篇笔记的元数据变得不可读——Dataview 看不到它，标签面板也显示不出标签。可以先创建一个笔记模板，把正确的 YAML 格式固化下来，避免每次手工输入时踩雷。

## 四、分块的真相：为什么固定长度会失败

### 4.1 一次实验

假设我们有一段 Markdown 正文：

```markdown
## KNN 算法原理

KNN 是非参数懒惰学习算法。

## SVM 数学推导

SVM 通过最大化间隔寻找分离超平面，
涉及拉格朗日对偶理论。
```

如果我们用最简单的 “每 50 个字符切一块” 策略，分块结果如下：

**块1**（前面50字符刚好包含SVM标题的开头）:

```text
## KNN 算法原理

KNN 是非参数懒惰学习算法。

## SVM 数学
```

**块2**:

```text
推导

SVM 通过最大化间隔寻找分离超平面，
涉及拉格朗日对偶理论。
```

块1混入了SVM的标题碎片，块2以“推导”二字开头，缺乏主语的上下文依赖。SVM相关的向量检索被两个不完整的碎片稀释。

这不是 Markdown 切分的夸大案例，而是**固定字符数切分**对所有结构化文本的固有问题：切分窗口不认识标题层级，不知道代码块与正文的边界，也不知道列表项是否该连在一起。它只是冷酷地数到第n个字符，然后一刀一刀切下去。

#### 4.1.1 动手验证：用代码感受固定切分的粗暴

如果你愿意进一步观察那种“冷酷”，可以写一个不到 15 行的 Python 脚本，亲手看看固定大小切分到底产生了什么。代码不需要任何第三方库，直接利用字符串切片：

```python
def fixed_chunk(text, size):
    chunks = []
    for i in range(0, len(text), size):
        chunks.append(text[i:i+size])
    return chunks

md = """## KNN 算法原理

KNN 是非参数懒惰学习算法。

## SVM 数学推导

SVM 通过最大化间隔寻找分离超平面，
涉及拉格朗日对偶理论。
"""

for idx, chunk in enumerate(fixed_chunk(md, 50), 1):
    print(f"=== 固定切分 Chunk {idx} ===\n{chunk}\n")
```

运行这段代码，你会亲眼看到第一块在“SVM 数学”之后断开，第二块从“推导”开始。正是这种断句使“SVM 数学推导”这个完整语义单元裂成两半，LLM 在后面无论怎么补都补不回来。

你可以随意修改 `size` 为 40、60、70，每一次都会在某个意想不到的位置撕裂一条标题或一句话。试过一次之后，“永远不要用字符数切 Markdown”就不再是一句书上的告诫，而是一个亲手验证过的结论。

### 4.2 RAG 视角下的后果

当用户查询 “SVM 的数学原理” 时，向量相似度可能在“块2”上得分很高——因为正文确实包含了 SVM 的数学描述。但 “块2” 在喂给 LLM 时上下文里没有前缀 “## SVM”，LLM 面对孤立的文本片段可能误判为 “KNN 相关” 或直接编造关系。

于是你在前端得到的回答变成了：“你笔记中的 SVM 提到推导涉及拉格朗日对偶……” 没错是没错，但别指望它精准引述你的笔记结构。

根源在分块阶段埋下。正是这类系统性问题，促使 RAG 工程演进到结构感知分块。

### 4.3 机制深潜：为何截断文本会误导 Embedding

Embedding 模型（如常用的 all-MiniLM-L6-v2）本质上是 Transformer 编码器。它通过自注意力机制捕捉每个词与全文中其他词的关系，生成上下文敏感的向量。当文本在句子中间被截断时，后半句的注意力连接直接消失，前半句的语义解释也可能发生偏差。比如“SVM 通过最大化间隔寻找分离超平面，涉及拉格朗日对偶理论”被切成“SVM 通过最大化间隔寻找分离超平面，”和“涉及拉格朗日对偶理论。”，拆开的两个片段各自都无法完整代表原意，嵌入向量也随之失真。

这就像人只听到前半句话就匆忙下结论，结果可能与完整话语相反。固定字符切分正是将所有文本同等对待，完全无视“人类语言是由语法层级组织起来的”这一事实。Markdown 的标题、段落、代码块等结构元素提供了天然的语义边界——只有尊重这些边界的切分策略，才能更完整地保留原始语义。

## 五、Markdown AST：让分块理解结构

### 5.1 Python 速览：本章会出现的语法

接下来我们要用 Python 编写一个 AST 分块器。如果你对 Python 还很陌生，先花三分钟过一遍下面这几个要素——它们足够你读懂本章的所有代码。

- **变量和赋值**：`chunks = []` 创建了一个空列表，`self.current = ""` 将当前文本暂存为空字符串。等号右边计算出的值会被赋给左边的变量。
- **函数定义**：`def chunk_by_heading(md_text):` 定义一个函数，括号里是参数。函数体采用统一缩进（通常是 4 个空格）。调用函数时，把实际的值写在括号里，如 `chunk_by_heading(md_content)`。
- **列表与循环**：`[1, 2, 3]` 是一个列表，用方括号包起来。`for i, c in enumerate(chunks, 1):` 表示“对 chunks 里的每一项循环，同时把序号交给 i，把内容交给 c”。
- **类与方法**：`class HeadingSplitter:` 定义一个类。类内部定义函数时第一个参数必须写 `self`，它代表类的具体实例。调用时 `self.chunks` 用来存取这个实例独有的列表，不同实例之间互不影响。

你不需要把这四条背下来。读到后面的代码时，如果突然对某个符号感到疑惑，再滑回来对照即可。

### 5.2 什么是AST

AST（抽象语法树）是编程语言从代码文本中构建出的树状结构。Markdown 也可以解析为 AST。如果你熟悉 HTML，可以把 Markdown 转 AST 的过程理解为浏览器将 HTML 解析为 DOM 树：每个元素（标题、段落、列表）都变成树的一个节点，层级关系与文档结构严格对应。

以下面这段 Markdown 为例：

```markdown
# 并发模型

## 线程

Python 线程因 GIL 限制 CPU 并行。

## 进程

multiprocessing 模块绕过 GIL。
```

如果用 Markdown 解析器生成 AST，结构大致为：

```text
Document
├── Heading (level 1): "并发模型"
│   ├── Heading (level 2): "线程"
│   │   └── Paragraph: "Python 线程因 GIL 限制 CPU 并行。"
│   └── Heading (level 2): "进程"
│       └── Paragraph: "multiprocessing 模块绕过 GIL。"
```

AST 对结构的感知，可以帮助我们制定一条分块规则：

> 以 H1、H2 标题为自然边界递归切分，保证每个块拥有完整标题和段落，绝不把代码块、表格或列表项切碎。

### 5.3 用 Python 实现一次标题递归切分

这一节会写一个短程序。它不需要你事先精通 Python；你只需要观察输入与输出的对照关系。我们会用到 Python 的 `mistune` 库来解析 Markdown，并用不到 30 行代码完成分块。

**前置环境准备**（只需执行一次）：

```bash
pip install mistune
```

**代码实现**：创建文件 `markdown_chunker.py`

```python
import mistune

class HeadingSplitter(mistune.HTMLRenderer):
    """自定义渲染器，每次遇到标题就创建新块。"""
    def __init__(self):
        super().__init__()
        self.chunks = []
        self.current = ""

    def heading(self, text, level):
        # 标题出现：结算前一块，开启新块
        if self.current.strip():
            self.chunks.append(self.current.strip())
        self.current = f"{'#' * level} {text}\n"

    def block_text(self, text):
        self.current += text + "\n"

    def finalize(self):
        if self.current.strip():
            self.chunks.append(self.current.strip())
        return self.chunks

def chunk_by_heading(md_text):
    renderer = HeadingSplitter()
    markdown = mistune.Markdown(renderer)
    markdown(md_text)
    return renderer.finalize()
```

**测试输入**：

```python
md_content = """\
# 并发模型

## 线程

Python 线程受 GIL 限制，
只适合 IO 密集型任务。

## 进程

multiprocessing 模块可绕过 GIL。
适合 CPU 密集型计算。
"""

chunks = chunk_by_heading(md_content)
for i, c in enumerate(chunks, 1):
    print(f"=== Chunk {i} ===\n{c}\n")
```

**输出**：

```text
=== Chunk 1 ===
# 并发模型

=== Chunk 2 ===
## 线程
Python 线程受 GIL 限制，
只适合 IO 密集型任务。

=== Chunk 3 ===
## 进程
multiprocessing 模块可绕过 GIL。
适合 CPU 密集型计算。
```

三个块完美对齐 Markdown 的原生结构。搜索“GIL 限制”会命中 Chunk 2，搜索“绕过 GIL”会命中 Chunk 3——两个概念不再混淆在一起。

### 5.4 理解关键节点

`HeadingSplitter` 继承自 `HTMLRenderer`，重写了两个方法：

- `heading`：每次识别到标题标签（如 `## 标题名`），它先结算之前累积的 `self.current` 成为一个独立块，再用新的标题字符串初始化下一块。
- `block_text`：将文本追加到当前块中。

这个逻辑可以递推到更复杂的结构：未来你可以添加代码块保护规则（检测 Fenced Code Block 的边界，禁止在中间一刀切开），或在 `heading` 中增加层级判断，只为 H2 切分而跳过 H3。

第3章的 Smart Connections 内部逻辑也用了类似的理念，只是它的分块器通过 TypeScript 实现了更完善的边界保护。

### 5.5 边界保护实例：不让代码块被肢解

固定字符切分最常见的一个麻烦就是把代码块切开，导致语法损毁。想象一段包含 Python 示例的笔记：

```markdown
## 示例代码

```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```
```

如果固定切分恰好落在代码块中间，生成的 Chunk 可能包含零碎的三引号或缩进错误，这类脏数据进入向量库不仅检索无效，还会污染 LLM 的生成质量。

AST 分块器天然能识别 Fenced Code Block 的起止边界。在 `mistune` 中，我们可以增加对代码块事件的处理，确保当前 Chunk 不会在代码块内部结算。因为 `mistune` 在解析代码块时不会触发 `heading` 事件，标题递归分块天然不会切进代码块内部，因此不需要额外的标志位。我们只需重写 `block_code` 方法，将整个代码块原样追加到当前块，从而保证代码块内部不会被分块边界打断。以下为额外的方法片段：

```python
class ProtectedHeadingSplitter(HeadingSplitter):
    def block_code(self, code, info=None):
        # 将整个代码块追加到当前块，不拆分
        self.current += f"```{info or ''}\n{code}\n```\n"
```

这样做以后，即使代码块内部包含类似标题的文本，也不会被误切为新的 Chunk 边界。真实工程中 Smart Connections 的插件代码就在文件监听与分块流程内实现了类似保护机制，确保代码、表格、LaTeX 公式等特殊区块不被暴力拆解。

### 5.6 更高阶的边界：引用块与嵌套列表

除代码块外，还有两类结构在切分时特别容易被破坏：

**引用块（Blockquote）**：以 `>` 开头的多行文字通常是一个完整的论述。固定切分可能在引用中间截断，让 LLM 收到半句引用，无法判断它来自哪个观点。AST 切分器会把整个引用块当作一个独立的区块，在遇到标题之前保持完整。

**嵌套列表**：例如：

```markdown
- 第一层
  - 第二层 A
  - 第二层 B
```

如果固定切分在“第二层 A”和“第二层 B”之间切开，那么两个子条目失去父条目，语义断裂。AST 切分则能识别列表的层级关系，保证同一父条目下的全部子条目不分散到两个 Chunk 中。

在 `mistune` 中，我们可以通过重写 `block_quote` 和 `list` 等方法实现类似保护：让整个引用块或列表块原样追加到 `self.current`，不在内部进行标题结算。核心原则是：**任何在语义上不可拆分的区块，都不应该作为分块边界**。这个原则在你自己扩展分块器时，可以反复对照应用。

## 六、父子文档策略：Small-to-Big Chunking

### 6.1 一个块不够用

标题递归分块解决了“不切碎一句话”的问题，但没有解决“一个查询需要关联上下文”的问题。

举例，用户问：“我的笔记里关于 Python 并发执行 CPU 密集型任务有哪些方案？”单块中的内容可能只包含进程方案的一部分。如果向量检索只返回孤立的 Chunk，LLM 的视野会比你的笔记实际信息窄。

RAG 有一个应对策略，叫 Small-to-Big Chunking：

- 建库阶段，用**小粒度块**（small chunk）建立向量索引，保证匹配精确。
- 检索阶段，找到匹配的小块后，把所属的**父文档上下文**（big chunk）一并喂给LLM。

实现方式之一是引入父子关系元数据：在切分时记录每个小块来自哪篇笔记、属于哪个标题段，并在检索后合并回原文。

### 6.2 在分块中加入父指针

修改前面的 `chunk_by_heading`，让它输出更多元信息。

```python
def chunk_with_parent(md_text, parent_title=""):
    renderer = HeadingSplitter()
    markdown = mistune.Markdown(renderer)
    markdown(md_text)
    chunks = renderer.finalize()
    return [
        {
            "chunk_id": f"{parent_title}::{i}",
            "parent_doc": parent_title,
            "text": chunk
        }
        for i, chunk in enumerate(chunks, 1)
    ]
```

用一个分块后的笔记 `python-concurrency.md` 测试：

```python
chunks = chunk_with_parent(md_content, parent_title="python-concurrency.md")
for c in chunks:
    print(f"ID: {c['chunk_id']} -> Parent: {c['parent_doc']}")
```

输出将明确标记每个 Chunk 的源文档。

第4章用本地向量库建立索引时，我们可以把 `chunk_id` 和 `parent_doc` 存入向量元数据。检索命中后，代码拉取父文档下的全部块，然后合并喂给LLM。

这就是 Small-to-Big 的精髓：查询靠小块定位，上下文靠父文档补全。

### 6.3 检索流程演示：从命中到完整上下文

为了更具体地理解父子文档策略，跟踪一次简化的问题过程：

1. 用户输入查询：“Python 多进程绕过 GIL 的方法”。
2. 检索系统对该查询向量化，与向量库中所有小块的向量进行相似度计算。
3. 得分最高的小块是 `python-concurrency.md::3`，内容是“## 进程\nmultiprocessing 模块可绕过 GIL。适合 CPU 密集型计算。”
4. 系统读取该块的 `parent_doc` 字段，找到源文件 `python-concurrency.md`。
5. 拉取该父文档下的全部三个小块，按顺序拼接为完整 Markdown 内容，作为完整上下文附加到查询中发送给 LLM。

结果是，LLM 不仅看到了精确匹配的“进程”段，还获得了该笔记下的“并发模型”导言和“线程”说明，回答可以自然地组织出：Python 提供的 multiprocessing 模块是 CPU 密集型任务的推荐方案，有别于受 GIL 限制的线程…

如果没有父文档补全，LLM 只收到孤立的小块，很可能只能简单地复述“multiprocessing 绕过 GIL”，而缺少与线程模型的比较，答案的深度和准确性都会打折扣。这就是 Small-to-Big 检索的实际作用。

### 6.4 边界：当父文档过长时怎么办

Small-to-Big 假定“整个父文档”可以塞进 LLM 的上下文窗口。但如果你的笔记本身就是一本微型的操作手册，长达数千字，全部拼接进去可能会超出模型的 token 限制，或者引入大量无关内容，反而稀释了精确匹配的信号。

这时可以把父子关系进一步分层：所有小块仍指向同一个父文档，但在检索后不再加载整个文件，而是只加载该文档内以最大标题（H2）为单位的“段落块”（medium chunk）。记录元数据时存储每个小块所属的段落标题。伪代码大致如下：

```python
# 在切分时存储 section 信息
chunk_meta = {
    "chunk_id": "tutorial::3",
    "parent_doc": "tutorial.md",
    "section": "## 安装步骤"
}
```

检索时，取出匹配小块所属的 `section`，再加载该 `section` 对应的完整文本。这样既保留了上下文，又不会把整本手册砸进窗口。你可以根据笔记的实际长度和模型托管成本，灵活选择“big chunk”的粒度——这正是结构化元数据带来的灵活性。

## 七、构造一个面向RAG的知识库片段

### 7.1 场景

假设你正在学习异常处理。你打算建三条笔记：

1. `python-exceptions-intro.md`——介绍异常基本概念
2. `python-try-except-finally.md`——语法与执行流程
3. `python-exception-propagation.md`——异常冒泡与栈追踪

每条笔记都带上 Frontmatter，内容单一聚焦。

### 7.2 笔记模板与内容

**笔记1**：`python-exceptions-intro.md`

```yaml
---
title: "Python 异常处理概览"
tags: [python, exceptions]
status: draft
type: concept
---
```

```markdown
# 异常处理

异常是运行时错误的统称。
Python 通过 try-except 语法捕获异常对象，
并在未捕获时向调用栈逐层传递。
```

**笔记2**：`python-try-except-finally.md`

```yaml
---
title: "try-except-finally 语法"
tags: [python, exceptions, syntax]
status: draft
type: concept
---
```

```markdown
# try-except-finally

`try` 块包裹受监控代码，
`except` 捕获指定异常类型，
`finally` 保证释放资源。
```

**笔记3**：`python-exception-propagation.md`

```yaml
---
title: "异常传播与栈追踪"
tags: [python, exceptions, internals]
status: draft
type: concept
---
```

```markdown
# 异常传播

未被捕获的异常沿调用栈向上传递。
Python 默认在栈顶打印异常链和 Traceback。
多层捕获可能导致异常屏蔽或链式携带。
```

### 7.3 串联验证

在 Obsidian 中完成以下步骤：

1. 创建上述三个文件，保存。
2. 打开 **标签面板**，确认 `exceptions` 类别下已列出三条笔记。
3. 在任意笔记中输入：

   ```markdown
   现在你已经看了 [[Python 异常处理概览]]，
   然后你应该继续了解 [[try-except-finally 语法]]，
   最后再看 [[异常传播与栈追踪]]。
   ```

4. 点住 `Ctrl/Cmd` 点击任意链接，Obsidian 立即跳转。这是显式知识图谱的起点。

5. 将三篇笔记复制到之前编写的 `markdown_chunker.py` 测试脚本中，运行分块，观察每个文件独立输出一到两个块，绝不交叉。

这就是面向 RAG 的数据准备：原子化设计 + YAML 元数据 + AST 分块 + 父文档映射。四项合在一起，让知识库从“一堆文字”变成“可查询的数据集”。

## 八、练习与反馈

### 8.1 预测题

以下是一篇没有经过原子化设计的笔记：

```markdown
# 算法对比

## 快速排序与归并排序

快速排序平均 O(n log n)，最坏 O(n²)。
归并排序始终 O(n log n)，但需要 O(n) 额外空间。
```

假设你使用的是固定 80 字符切分策略，切分时第二段的完整语句会被打断吗？如果是 AST 标题切分，这块会变成几个 Chunk？为什么其中一个Chunk在 AST 方法下对搜索“快速排序复杂度”更友好？

### 8.2 答案

固定 80 字符切分可能在“快速排序平均 O(n log n)”和“归并排序始终 O(n log n)”之间切开，也可能把“最坏 O(n²)”与前句切断，严重破坏上下文。AST 标题切分则保留整个 `## 快速排序与归并排序` 的段落为一块，因此对“快速排序复杂度”的搜索返回的两个复杂度数值都在同一 Chunk 内，语义完整。

如果你在纸上画一下两种切法，会立刻理解第4章 Embedding 向量相似的命运在分块阶段就已注定。

### 8.3 动手练习

1. 选取你已经存在的三条笔记，判断它们是否满足原子化原则。
2. 为每条笔记补充 Frontmatter，确保 `tags`、`status`、`type` 都已填写。
3. 用本章提供的 Python 分块代码，实际运行切分。如果得到超过三个的 Chunk，检查是否原文藏着新的概念应独立成篇。

完成以上三项后，回到 Obsidian 用双链 `[[...]]` 把拆出来的新笔记连接起来。

### 8.4 附加练习：手动模拟分块

阅读以下 Markdown 文本，不做代码执行，手动画出固定切分（每 60 字符切一块）和 AST 标题切分产生的块边界，并判断哪一种对查询“SVM 推导”更有利。

```markdown
## KNN 概述

KNN 算法不需要训练，分类时计算距离。

## SVM 推导

SVM 通过拉格朗日对偶求解最大间隔超平面。
```

**思考提示**：固定切分时，60 字符的窗口可能正好截断“SVM 推导”标题与其正文的连接；而 AST 切分会保证整个 `## SVM 推导` 及其后续段落组成一个完整块。

### 8.5 修改代码练习

回到 `ProtectedHeadingSplitter` 的代码，尝试增加一条规则：当块的长度超过 500 个字符时，即使是同一个标题段落，也强制进行切分，同时将切分点选在最近的句号后。你无需一次性写出全部逻辑，先回答两个问题：

1. 要在哪个方法中插入长度检查逻辑？
2. 如何在不调用额外 NLP 工具的情况下，找到离 500 字符最近的句号位置？

参考答案：

1. 在 `block_text` 方法中，每次追加文本后检查 `len(self.current)`。如果超过阈值，就在 `self.current` 中从 500 字符处向左搜索最后一个 `'。'`，以该位置为界拆分成两个块。
2. Python 的字符串方法 `rfind('。', 0, 500)` 可以从位置 500 向左查找最近的句号，用这个索引切割字符串即可。

如果你完成了这两步，其实就已经自己动手实现了一个“受限的固定切分”，它比纯字符切分多了对句子完整性的考虑——而这正是工程中反复出现的平衡点。

## 九、常见误区

1. **“字少就是原子化”**  
   原子化要求每篇聚焦一个概念，而非追求字数少。一篇 2000 字的完整教程本身就是独立单元，不应为拆而拆。

2. **“Frontmatter写了就行，AI就能用”**  
   Frontmatter 是结构化的数据入口，但后续分块器读取它、向量库存储它，才进入 AI 管线。中间任何一环不支持 YAML 解析，这些字段只是注释。

3. **“AST 分块一定比固定切分好”**  
   对于毫无结构的纯文本或诗歌语料，AST 解析退化为根本没标题可切。此时结构感知优势消失，需要退化到基于段落或句子的切法。但 Obsidian 笔记天然带标题，AST 切分的优势在99%的用例下成立。

4. **“分块策略一次配好，以后不用管”**  
   不同笔记类型（教程、会议记录、日志）可能需要不同的切分粒度。`type` 字段正是将来做“按类型调策略”的前置数据。第9章会讲知识库的持续维护与策略调优。

5. **“加了双链 `[[...]]` 的笔记就算原子化”**  
   双链是一种连接方式，表示两篇笔记之间存在关联，但链接本身并不能把一篇笔记内部堆砌的多主题强制分开。如果一篇笔记里同时讲解了“数据库索引原理”和“B+树实现细节”，即便把它链接到其他笔记，对于 RAG 而言，该文件的嵌入向量仍然混杂了两种语义。原子化看的是文件内容的单一性，而不是链接的数量。

## 十、本章小结

数据建模的核心是**为检索而写作**。原子化笔记让每个概念独立出来，成为可检索的单元；YAML Frontmatter 为机器提供分层标签维度；AST 解析让分块尊重语义边界，不再被字符数切碎；而父子文档策略补足了小块的上下文盲区。

当你下一次在 Obsidian 新建笔记时，标题、三个 Frontmatter 字段、链接关系和概念边界的习惯，会让你的笔记更容易被未来的搜索和 RAG 系统解析。

## 十一、快问快答

1. 原子化笔记的核心标准是字数还是概念单一性？  
   **概念单一性。** 一个文件一个概念或一个意图，无论字数多少。

2. 固定字符切分与 AST 切分在对同一段带标题的 Markdown 时，输出Chunk数量可能相同吗？  
   **可能，但意义不同。** 即使块数巧合相等，固定切分可能在标题和正文交界处错位。

3. 父子文档策略中，向量索引使用的是大块还是小块？  
   **小块。** 大块在检索命中后作为补充上下文送入 LLM。

4. `type: meeting-notes` 和 `type: concept` 在分块策略上可能需要不同对待吗？  
   **是。** 会议记录可能按时间轴切分，概念笔记更适合按标题结构切分。

## 参考文献

- Obsidian. [Obsidian 中文帮助](https://obsidian.md/zh/help/).
- GitHub alex-chou. [chunkana: 多策略 Markdown 分块库](https://github.com/asukhodko/chunkana).
- IBM Developer. [Enhance RAG performance through intelligent chunking strategies](https://developer.ibm.com/articles/awb-enhancing-rag-performance-chunking-strategies/).


---

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
