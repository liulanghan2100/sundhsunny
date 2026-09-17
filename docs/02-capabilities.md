# 能力清单（engine/mcps）

`engine/mcps/` 下有 **42 个功能模块**，主流程（`hub.py ask`）不经过它们，
但每个都能独立启动、独立调用。

这份清单回答：**"我想做某件事，包里有没有现成的？"**

---

## 怎么用

### 看有哪些

```
python hub.py mcps                 列出全部
python hub.py mcps queue           按名字过滤
```

### 直接导入调用（推荐）

不用起进程、不用注册。42 个模块一次性全部导入只需 **2.2 秒**：

```python
import sys
sys.path.insert(0, "engine/mcps")
sys.path.insert(0, "engine/memory")   # 部分模块需要
sys.path.insert(0, "core")            # 部分模块需要

import preflight_bundle_mcp.common as pf
result = pf._bundle(project="x", task="部署上线",
                    operation="deploy", risk="L3", context={})
```

每个模块真正干活的是内部的 `_xxx` 函数，`@mcp.tool` 装饰的只是外壳。

### 起 MCP 进程（仅在需要给外部客户端用时）

```python
import sys
sys.path.insert(0, "engine/mcps")
import task_queue_mcp.common as c
c.build_server().run()      # stdio 模式
```

**代价对比**（实测）：

| 方式 | 内存 | 启动 |
|---|---|---|
| 42 个全起进程 | 42 × 56MB ≈ 2.3 GB | 42 × 2.4s ≈ 100 秒 |
| 直接导入全部 | 单进程共享 | 2.2 秒 |

---

## 依赖的 sys.path

绝大多数模块只需 `engine/mcps`。少数依赖更多的，已在各自 `run_*.py` 里写好：

| 需要的路径 | 哪些模块要用 |
|---|---|
| `engine/mcps` | 全部 |
| `engine/memory` | `memory_retrieval_mcp` / `product_os_mcp` / `video_generation_mcp` / `offline_upgrade_mcp` 等 |
| `core` | 同上（治理核的校验、审批、锁、预算）|

依赖最多的是 `task_queue_mcp`（跨 4 个包内位置）。

---

## 全部模块

按用途分组，共 42 个、270 个工具。

### 一、任务治理（10 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `control_plane_mcp` | 策略检查、自主权决策、审计事件 | 8 |
| `mandatory_runtime_hook_mcp` | 强制路由规划、合规校验 | 5 |
| `preflight_bundle_mcp` | 执行前统一检查 | 3 |
| `side_effect_admission_mcp` | 副作用准入票 | 4 |
| `capability_profile_mcp` | 能力画像、动作许可检查 | 4 |
| `policy_consistency_auditor_mcp` | 策略一致性审计 | 3 |
| `approval_interrupt_mcp` | 审批中断 | 6 |
| `autonomy_level_assessor_mcp` | 自主权级别评估 | 3 |
| `cost_budget_mcp` | 成本预算 | 5 |
| `production_readiness_mcp` | 生产就绪度 | 3 |

### 二、任务队列与调度（3 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `task_queue_mcp` | 队列状态、入队、自启动治理 | **20** |
| `auto_trigger_mcp` | 自动触发 | 4 |
| `workflow_runtime_mcp` | 工作流运行时 | 8 |

### 三、验证与复盘（5 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `completion_verifier_mcp` | 按证据验证完成度、签发证书 | 3 |
| `failure_replay_mcp` | 记录失败、蒸馏教训、建规避计划 | 7 |
| `compiled_correction_mcp` | 记录纠正、编译成检查规则 | 5 |
| `evaluation_harness_mcp` | 评测框架 | 5 |
| `local_regression_gate_mcp` | 本地回归门禁 | 3 |

### 四、记忆与知识（3 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `memory_consolidation_mcp` | 记忆分层、冲突检测、健康报告 | 6 |
| `memory_retrieval_mcp` | 记忆检索 | 3 |
| `research_mcp` | 研究 | 9 |

### 五、审计与可观测（5 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `audit_hash_chain_mcp` | 审计哈希链（证据链完整性）| 4 |
| `trace_observability_mcp` | 链路可观测 | 9 |
| `tool_lifecycle_tracing_mcp` | 工具生命周期追踪 | 10 |
| `health_check_mcp` | 健康检查 | 5 |
| `backup_integrity_mcp` | 备份完整性 | 4 |

### 六、Agent 运行时（6 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `agent_orchestration_mcp` | Agent 编排 | 13 |
| `agent_runtime_kernel_mcp` | Agent 运行时内核 | 9 |
| `runtime_integration_mcp` | 集成任务环、导出状态、建备份 | 6 |
| `runtime_middleware_mcp` | 按任务类别搭中间件栈 | 4 |
| `hook_runtime_mcp` | 工具调用前后、停止时的钩子链 | 6 |
| `long_running_session_mcp` | 长会话 | 7 |

### 七、决策与推理（2 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `decision_workbench_mcp` | 决策工作台 | 12 |
| `mathematical_reasoning_mcp` | 数学推理 | 8 |

### 八、领域与交付（4 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `tia_template_compiler_mcp` | **TIA 模板编译**（西门子）| 9 |
| `git_ci_mcp` | Git / CI | 14 |
| `offline_upgrade_mcp` | 离线升级 | 5 |
| `video_generation_mcp` | 视频生成 | 8 |

### 九、看板与准入（3 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `dashboard_mcp` | 采集数据、生成看板 HTML | 6 |
| `agentops_dashboard_mcp` | AgentOps 看板 | 3 |
| `cognitive_intake_mcp` | 请求分类 A/B/C/D、建执行卡 | 6 |

### 十、其他（1 个）

| 模块 | 干什么 | 工具 |
|---|---|---|
| `product_os_mcp` | 产品 OS | 11 |

---

## 校验状态（2026-09-16）

| 项 | 结果 |
|---|---|
| 模块总数 | **42** |
| 可启动 | **42 / 42** |
| 工具总数 | **270** |
| 依赖外部包 | **0 个** |
| 体积合计 | 约 2.0 MB |

全部模块只依赖：Python 标准库、`mcp`（第三方）、包内 `_shared` 公共库、
以及包内其他模块。**没有外部依赖，换机器可直接用。**

---

## 与主流程的关系

```
hub.py ask  -> 治理核 -> 记忆/知识/图谱 -> 简报 -> 门禁
                  │
                  └── 主流程只用到这里

engine/mcps/*  ->  42 个模块全部在此之外，独立可用
```

**为什么主流程不经过它们**：这些模块来自源库的"Agent OS 完整版"，
设计前提是有一整套运行时（队列守护、钩子注入点、中间件框架）。
hub 是轻量编排层，直接接入会产生大量耦合。

**它们的价值**：作为**能力储备**。需要某个功能时直接导入调用，
不必起进程、不必注册。
