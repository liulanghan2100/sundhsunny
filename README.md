# agentos-hub

单一任务入口的个人 Agent 工作台。一个任务进来，走同一条流水线：

    准入分级 -> 三源检索（经验/知识/代码图谱）-> 任务简报 -> 门禁 -> 经验回流

## 快速开始

```bat
python -m pip install -r requirements.txt
python hub.py doctor
python hub.py ask "把 A 股日报生成自动化"
```

## 五个核心能力

| 能力 | 命令 | 说明 |
|---|---|---|
| 单一任务入口 | `hub.py ask "..."` | 分级 + 三源检索 + 简报 + 回流，一条命令走完 |
| 经验记忆 | `hub.py recall "..."` | 458 条真实经验；4 种检索（关键词/语义/向量/FTS） |
| 学习蒸馏 | `hub.py learn` | 把散落经验提炼成可复用教训 |
| 知识库 | `hub.py kb "..."` | quarantine -> trusted 晋升，带来源可溯源 |
| 代码知识图谱 | `hub.py graph search_graph ...` | 符号级代码检索（外部 MCP） |
| 技能路由 | `hub.py skills --keyword 仓颉` | 支持中文关键词 |
| 门禁 | `hub.py gate strategy plan_next ...` | manual-gates 27 节点，可直接跑 |

## 目录

```
agentos-hub/
├── hub.py              唯一入口（11 个命令）
├── config.yaml         所有路径配置
├── requirements.txt    依赖声明（不打包依赖）
├── core/               治理核：准入 / 风险分级 / 宪法 / 审批 / 恢复
├── engine/             引擎：记忆 / 知识库 / 16 个功能模块
├── skills/             技能资产（35 个 active）
├── data/               运行时数据（jsonl 为真相源，sqlite 可重建）
├── tools/              代码图谱引擎与索引
└── _archive/           历史备份
```

**每个目录装了什么、命名为什么有个别不一致、换机器怎么处理，
详见 [DIRECTORY.md](DIRECTORY.md)。**

## 设计取舍（相对 agentos-slim 的修正）

1. **不打包依赖**。原版把 mcp 1.30 塞进 `_runtime_deps`（52MB），并被迫改
   `gate.py` 源码打补丁，只为兼容一个本就该换掉的解释器。这里只声明版本：
   `mcp>=1.28,<2.0`。

2. **路径全部配置驱动**。原版 `manual-gates/common.py` 用 `parents[4]` 推导
   `PROJECT_ROOT`，会把门禁验收命令的工作目录锚在骨架包自身，而不是用户的
   真实项目目录。这里由 `config.yaml` 显式给出。

3. **doctor 严格只读**。原版 doctor 会跑 `plan_next` 做冒烟，那会创建项目状态，
   与其自称的只读相矛盾；且异常分支的计数有 bug，导致 FAIL 重复计数。这里只做
   静态检查，计数统一走一个 `_chk()`。

4. **中文关键词可检索**。原版只匹配英文技能名，`--keyword 仓颉` 必然返回 0 条。
   这里叠加 `skills/skill_aliases.json`（38 个技能的中文别名）。

5. **能力惰性加载**。只用 `ask`/`skills`/`doctor` 时不需要装 mcp；只有真正调用
   记忆或门禁时才 import。

## 依赖

```
mcp>=1.28,<2.0    门禁与记忆引擎的运行时；2.x 移除了 mcp.server.fastmcp
PyYAML>=6.0       配置读取
jsonschema>=4.0   任务卡校验
```

## 已知边界

- 代码知识图谱依赖外部 `codebase-memory-mcp`。若目标机器没有该工具，
  `hub.py graph` 会返回结构化错误，不影响其它能力。
- 知识图谱的 `index_repository` 在部分环境下会崩溃（连单文件目录也会），
  属该工具自身问题；已有索引的检索不受影响。
- 记忆引擎的 FTS 检索对中文效果有限（分词限制），中文场景请用
  `vector_search_memory`（`hub.py recall` 默认优先走向量）。

## 来源

核心件从 `MCPCreate20260719` 搬迁（只读源仓库，零改动）：治理核 32 文件、
经验记忆 458 条、知识库 26 条、技能 35 个 active、门禁 27 节点。

## 代码知识图谱：如何嵌入的

`codebase-memory-mcp` 是一个 **260.7 MB 的独立 PE 可执行文件**（不是 Python 包），
本包采用「**包内自带 + 自动回退**」的方式嵌入。

### 目录布局

```
tools/codebase-memory-mcp/
├── bin/codebase-memory-mcp.exe      260.7 MB  工具本体
└── cache/                            66.9 MB  已建好的索引库
    ├── _config.db
    ├── MCPCreate20260719.db                  58.7 MB  主仓库图谱（39430 节点）
    ├── ...-AutoRobot.db                       3.3 MB
    └── OpenNiss.TiaExport.V21.db               4.9 MB
```

### 查找顺序（`hub.py graph_candidates`）

| 优先级 | 位置 | 说明 |
|---|---|---|
| 1 | `tools/codebase-memory-mcp/bin/` | **包内自带**，保证可独立带走 |
| 2 | `$CODEBASE_MEMORY_MCP_EXE` | 环境变量覆盖 |
| 3 | `graph.cli`（config.yaml） | 系统安装位置 |
| 4 | `~/.local/bin/` | 默认系统安装 |

任一路径不存在自动试下一个；全都不存在则图谱降级为 0 命中，
**不影响其余四项能力**（`graph_call` 返回结构化错误，不抛异常）。

### 缓存重定向（关键）

`codebase-memory-mcp` 默认从 `~/.cache/codebase-memory-mcp` 读索引。
实测发现只有 **`CBM_CACHE_DIR`** 这个环境变量能重定向（其他如
`CODEBASE_MEMORY_CACHE_DIR` / `CODEBASE_MEMORY_HOME` 均无效）。
`hub.py` 在调用时自动注入该变量，指向包内 `tools/.../cache`。

> 实测效果：接入包内缓存后，可检索的图谱从 1 个项目 / 2297 节点
> 提升到 **3 个项目 / 39430 节点**（原先一直在漏读系统缓存里的主库）。

### 已知限制：建索引会崩

在**本机**实测 `index_repository`（建新索引）连只含单个 `.py` 的目录都会崩溃：

```
{"status":"error","outcome":"exit_nonzero",
 "hint":"Indexing worker crashed on a file."}
```

排查结论：
- 与缓存目录被占用无关（用独立缓存目录同样崩）
- 与被索引内容无关（单文件目录同样崩）
- 属该工具自身的 worker 崩溃，**已建好的索引检索不受影响**

因此现状是：**包内 3 个图谱可搜，但暂不能为新项目建索引**。
目标机器上可尝试单独 `install` 一次再看是否恢复。

### 转移时压缩

exe 压缩率约 25.5%，整包可从 373 MB 压到约 180 MB：

```powershell
7z a -mx=9 agentos-hub.7z agentos-hub\
```

解压后可直接使用（无需额外安装步骤）。
