# 课程资源

## 来源政策

允许使用用户资料与公开官方资料

## 检索范围与使用边界

- Agent 会围绕课程核心概念、所用框架或工具的当前 API、相关标准或论文、项目实践与部署/安全边界检索资料。
- 每一条资料都必须说明其支撑的教学内容；关键事实、API 用法和规范不得只依赖未核验的社区文章。
- 资料是否可用以来源政策为准：只有政策允许时，才将社区教程作为补充阅读。

## Agent 检索与核验

任务定义确认后，Agent 会在这里写入检索计划、经筛选的资料和仍需人工补充的缺口。

## 用户补充资源

可在此登记链接、课程资料说明或上传附件的使用目的。

- [Obsidian 中文帮助 ](https://obsidian.md/zh/help/)
- [obsidian_tutorial](https://github.com/FDscend/obsidian_tutorial)
- [obsidian-ai-orange-book](https://github.com/alchaincyf/obsidian-ai-orange-book)
- [obsidian指南](https://obsidian.vip/zh/documentation/)
- [obsidian-3d-graph](https://github.com/Apoo711/obsidian-3d-graph)

<!-- agent-research:start -->
## 自动检索记录

- 本轮来源政策：允许使用用户资料与公开官方资料。
- 检索覆盖：核心概念、框架/API、标准或论文、项目实践，以及需要时的安全与部署边界。
- 使用方式：资料仅支撑其对应的事实、API 或实践；未核验社区资料不能作为关键事实的唯一依据。

### 本轮检索计划

- 检索理由：围绕课程九章内容制定检索方向，优先获取官方文档、协议标准、学术论文及核心开源项目说明。'Obsidian plugin API developer documentation'支撑第3章插件架构拆解，定位官方API与社区开发规范；'Markdown AST chunking strategy for RAG vectors'服务于第2章AST解析与分块，查找论文与最佳实践，避免固定长度切分缺陷；'Microsoft GraphRAG research paper and LightRAG implementation'对应第6章GraphRAG原理，需获取原始论文与轻量级实现文档；'Ollama OpenAI compatible endpoint local deployment embed models'覆盖第4章全本地部署，需Ollama文档与bge-m3等模型的官方说明；'Model Context Protocol MCP specification Anthropic'面向第8章MCP集成，必须基于Anthropic发布的协议标准；'RAGAS evaluation framework faithfulness answer relevance context precision'为第9章评估框架提供官方指标定义与使用指南；'Obsidian 3D graph plugin GitHub Apoo711'直接支撑新增的第7章3D关系图谱，指向核心社区插件的维护教程与配置说明。
- 检索词：`Obsidian plugin API developer documentation`
- 检索词：`Markdown AST chunking strategy for RAG vectors`
- 检索词：`Microsoft GraphRAG research paper and LightRAG implementation`
- 检索词：`Ollama OpenAI compatible endpoint local deployment embed models`
- 检索词：`Model Context Protocol MCP specification Anthropic`
- 检索词：`RAGAS evaluation framework faithfulness answer relevance context precision`
- 检索词：`Obsidian 3D graph plugin GitHub Apoo711`

### 已核验可用资料

- [Home - Developer Documentation](https://docs.obsidian.md/Home)（official）：Official Obsidian plugin developer documentation home, covering API basics, lifecycle, and core concepts to support plugin development practice.
- [Plugin - Developer Documentation](https://docs.obsidian.md/Reference/TypeScript+API/Plugin)（official）：Detailed Plugin class API reference defining load, save, unload hooks and metadata; essential for implementing custom plugins.
- [GitHub - asukhodko/chunkana: A multi-strategy Markdown chunking library ...](https://github.com/asukhodko/chunkana)（community）：Multi-strategy Markdown chunking library using AST parsing, supporting header, paragraph, and token splitting for preparing RAG vectors.
- [Enhance RAG performance through intelligent chunking strategies](https://developer.ibm.com/articles/awb-enhancing-rag-performance-chunking-strategies/)（community）：IBM article explaining intelligent chunking methods including structure-aware splitting of Markdown, improving retrieval relevance for RAG.
- [Project GraphRAG - Microsoft Research](https://www.microsoft.com/en-us/research/project/graphrag/)（official）：Microsoft Research project page for GraphRAG, linking to the research paper and overview, supporting graph-based RAG understanding.
- [GitHub - microsoft/graphrag: A modular graph-based Retrieval-Augmented ...](https://github.com/microsoft/graphrag)（official）：Official GraphRAG implementation, a modular library for building graph indices for retrieval-augmented generation, directly usable in course labs.
- [OpenAI compatibility - Ollama](https://docs.ollama.com/api/openai-compatibility)（official）：Ollama documentation for OpenAI-compatible endpoint, enabling local embedding model calls and chat completions in the course local deployment module.
- [Specification - Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18)（standard）：MCP specification defining client-server interaction, resources, prompts, and tools; foundational standard for integrating LLMs with external tools.
- [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol/modelcontextprotocol)（standard）：Official MCP repository containing the protocol specification and reference implementations, supporting practical understanding and integration.

### 检索备注

- Missing resources for LightRAG implementation: search results provided only GraphRAG items; no LightRAG repository or paper found.
- Missing resources for RAGAS evaluation framework (faithfulness, answer relevance, context precision): no results returned for the query.
- Missing resources for Obsidian 3D graph plugin by Apoo711: no results returned for the query.

<!-- agent-research:end -->
