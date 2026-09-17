# 文档索引

本目录放参考类文档。根目录只留两个通行约定的文件：
`README.md`（上手）和 `CHANGELOG.md`（版本记录）。

---

## 按目的找

| 我想…… | 看这份 |
|---|---|
| 了解整体架构、分层、整合建议 | [00-architecture.md](00-architecture.md) |
| 知道每个目录装了什么 | [01-directory.md](01-directory.md) |
| 查包内有哪些备用能力可调研 | [02-capabilities.md](02-capabilities.md) |
| 核对大文件有没有被改动 | [03-version-manifest.md](03-version-manifest.md) |
| 看全包体检结果与待办 | [04-audit-2026-09-16.md](04-audit-2026-09-16.md) |

---

## 各文档一句话

**[00-architecture.md](00-architecture.md)** —— 架构分析与整合建议

画出实际分层（运行时/治理/编排/引擎/资产），指出**执行缺口**：
治理核声明规则、Codex 有执行权，中间没接通。
给出分三档的整合建议，以及明确不建议做的事。

**[01-directory.md](01-directory.md)** —— 目录结构说明

逐个说明顶层目录的用途，含"现场指南"（想找什么去哪找）、
命名遗留（为什么 `skills-shared-candidate` 名不副实）、换机器处理步骤。

**[02-capabilities.md](02-capabilities.md)** —— 备用能力清单

`engine/mcps/` 下 42 个模块的用途、工具数、启动方式。
按"你可能想做什么"分组（任务治理/队列/验证复盘/记忆增强/运行时编排/任务准入）。

**[03-version-manifest.md](03-version-manifest.md)** —— 大文件指纹清单

未纳入版本管理的 7 个大文件（引擎、索引、记忆数据）的 SHA256 前 16 位，
用于换机器或日后核对完整性。含这些文件怎么迁移、怎么重建。

**[04-audit-2026-09-16.md](04-audit-2026-09-16.md)** —— 全包审计报告

15 项命令实跑结果、发现的漏洞与修复记录、冗余与命名问题、
整改优先级，以及"审批/恢复要不要接进主流程"的专项分析。
