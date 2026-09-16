# 目录结构说明

这份文档说明每个目录**是干什么的、里面装了什么、什么情况下会用到**。
目的是：无论隔多久回来看，或者换台机器，都能一眼找到东西在哪。

---

## 一、总览

```
agentos-hub/
├── hub.py               ← 唯一入口
├── config.yaml          ← 所有路径配置
├── requirements.txt     ← 依赖声明（换机器要装）
│
├── core/                ← 治理核：任务进来先过这里
├── engine/              ← 引擎：记忆、知识、工具
├── skills/              ← 技能资产
├── data/                ← 运行时数据（会增长）
├── tools/               ← 外部程序（大，不常动）
│
├── _archive/            ← 历史备份
├── CHANGELOG.md         ← 版本变更记录
├── VERSION-MANIFEST.md  ← 大文件指纹清单
└── README.md            ← 快速上手
```

一句话记住：**入口在根目录，能力在 core/engine/skills，数据在 data，大件在 tools。**

---

## 二、根目录文件

| 文件 | 作用 | 什么时候看 |
|---|---|---|
| `hub.py` | **唯一入口**，11 个命令 | 每天用 |
| `config.yaml` | 所有路径、门禁、图谱的配置 | 要改路径或开关时 |
| `requirements.txt` | 三个依赖：mcp / PyYAML / jsonschema | 换机器时 |
| `README.md` | 快速上手 | 第一次用 |
| `CHANGELOG.md` | 每版做了什么、为什么 | 想知道改了什么 |
| `VERSION-MANIFEST.md` | 大文件指纹，用于核对完整性 | 换机器、怀疑文件被改动 |

---

## 三、核心目录

### `core/` —— 治理核（任务的"安检口"）

任务进来第一步走这里，判断**这活能不能干、要多小心**。

```
core/
├── Agent_OS_Core/
│   ├── policy/           风险分级（L1/L2/L3）、深度策略
│   │   ├── action_pre_scan.py    动作词表扫描
│   │   ├── risk_classifier.py    定级
│   │   ├── depth_policy.py       定深度（要不要审批/复核）
│   │   └── unified_intake.py     总入口
│   ├── constitution/     宪法层（5 个规则文件 + 校验器）
│   ├── governance/       审批门（决策记录）
│   ├── recovery/         失败恢复（事故、回滚、策略）
│   ├── schemas/          数据契约校验
│   └── knowledge/        知识边界规则
└── _tests-integration/   跨核测试（不参与自检）
```

**关键点**：`constitution/` 里的 5 个 JSON 是**禁止修改**的（写入会被拦）。
它们是这个系统的"红线"——定义了什么能做、什么绝对不能做。

### `engine/` —— 引擎层（干活的部件）

```
engine/
├── memory/         经验记忆引擎
│   └── experience_memory_mcp/
├── knowledge/      知识库脚本
│   └── knowledge-base/scripts/   (add / query / promote / report)
└── mcps/           16 个功能模块
    └── _shared/    公共库
```

`engine/mcps/` 下每个 `*_mcp/` 是一个独立功能模块，比如：

| 模块 | 干什么 |
|---|---|
| `cognitive_intake_mcp` | 任务准入判断 |
| `task_queue_mcp` | 任务队列 |
| `dashboard_mcp` | 运行看板 |
| `failure_replay_mcp` | 失败回放 |
| `preflight_bundle_mcp` | 执行前检查 |

> 注：这些模块是从源库整包带过来的，`hub.py` 目前**只用到其中少数几个**。
> 其余的留在包里备用，不影响主流程。

### `skills/` —— 技能资产

```
skills/
├── manual-gates/              ← 门禁正本（27 节点手册）
├── knowledge-base/            ← 知识库技能
├── offline-upgrade/           ← 离线升级
├── mckinsey-structured-thinking/
├── nuwa-runbook/  darwin-runbook/
├── industrial-expert-dev/  expert-dev-p0/
├── agent-os-decision-workbench/
├── skills-shared-candidate/   ← 见下方"命名遗留"
└── *.json / *.tsv             ← 技能登记表
```

登记表说明：

| 文件 | 作用 |
|---|---|
| `active_skills.json` | 哪些技能在用（35 个）|
| `skill_aliases.json` | 中文别名（让中文关键词能匹配到英文技能）|
| `skill_registry.tsv` | 全量清单（含描述）|
| `skill_status.json` | 每个技能的状态 |

---

## 四、数据目录

### `data/` —— 运行时数据（会不断增长）

```
data/
├── memory/         经验记忆
│   ├── memory.jsonl          ← 正文（真相源，不可再生）
│   ├── memory_index.sqlite   ← 关键词索引（可重建）
│   └── memory_vector.sqlite  ← 向量索引（可重建）
└── knowledge/      知识库
    ├── meta.jsonl            ← 条目元数据
    ├── index.sqlite          ← 检索索引
    ├── cases/                ← 已采信
    └── quarantine/           ← 待审
```

**重要**：`memory.jsonl` 是累积经验，**丢了就找不回来**，要单独备份。
两个 `.sqlite` 是索引，可以随时重建。

### `tools/` —— 外部程序

```
tools/codebase-memory-mcp/
├── bin/codebase-memory-mcp.exe   ← 引擎（260MB）
└── cache/                        ← 图谱索引（67MB）
```

这是代码知识图谱的引擎，单文件、零依赖、拷过去就能跑。

### `_archive/` —— 历史备份

```
_archive/2026-09-16/
├── hub.py.bak-*        每次改动前的快照
├── core/.../*.py.bak-*
└── data/memory/*.bak-* 记忆数据备份
```

启用版本管理后，**源码类备份已被 git 取代**，这里主要留**记忆数据的备份**
（它不在 git 里，是唯一的回退手段）。

---

## 五、命名遗留（已知的乱，如实说明）

包是从源库打包出来的，继承了几个**名不副实**的地方。
不影响使用，但看到时别被绕进去：

### 1. `skills/skills-shared-candidate/` 名字骗人

名字说"候选"，**实际装着 35 个主力技能**（还有 24 个已归档、3 个待审）。

原因：源库里技能分两处放，打包时整目录带过来了，名字没改。

**怎么理解**：`skills/` 根下的是"门禁、知识库"这几个特殊技能，
`skills-shared-candidate/` 下的是"其余全部技能"。

### 2. `manual-gates` 有两份

| 位置 | 状态 |
|---|---|
| `skills/manual-gates/` | **正本**（config 指向这里，244 个项目状态）|
| `skills/skills-shared-candidate/manual-gates/` | 副本（93 个项目状态）|

**用正本**。副本是源库遗留，已在技能登记表里标为 `replacement`。

### 3. `knowledge-base` 有两份

| 位置 | 状态 |
|---|---|
| `engine/knowledge/knowledge-base/` | **正本**（hub.py 用这个）|
| `skills/knowledge-base/` | 副本（脚本基本相同）|

### 4. `core/_tests-integration/` 为什么在核心目录

里面的测试验证**治理核与自治核的衔接**，需要包外的 AutoRobot 组件。
放在这里是因为它属于治理核的测试，但不能进包内自检——独立目录标清楚。

---

## 六、换机器时怎么办

| 目录 | 怎么处理 |
|---|---|
| `core/` `engine/` `skills/` | 直接复制，或从 git 拉 |
| `data/` | 复制（`memory.jsonl` 必须带）|
| `tools/` | 复制（引擎免安装）|
| `_archive/` | 可不带 |

复制后要做的两件事：

1. 装依赖：`python -m pip install -r requirements.txt`
2. 验证：`python hub.py doctor`（应显示 24/24）

---

## 七、想找东西时

| 想找 | 去哪 |
|---|---|
| 风险分级规则 | `core/Agent_OS_Core/policy/` |
| 什么绝对不能做 | `core/Agent_OS_Core/constitution/charter.json` |
| 我的经验记录 | `data/memory/memory.jsonl` |
| 某个技能定义 | `skills/` 或 `skills/skills-shared-candidate/` |
| 门禁 27 节点定义 | `skills/manual-gates/scripts/manual_mcp/manual_data.py` |
| 所有路径配置 | `config.yaml` |
| 改了什么 | `CHANGELOG.md` |
