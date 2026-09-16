---
name: hedge-fund
description: Run a multi-agent AI hedge fund analysis on A-share tickers using the local ai-hedge-fund codebase (agents: Buffett, Munger, Graham, Lynch, Druckenmiller, PEAD). Data comes from AkShare (free, no API key). Use when the user wants a multi-agent fund analysis, bull/bear thesis per ticker, deep-value/earnings-drift screening, or a fund-level decision memo on Chinese A-shares. Trigger words: 基金, 多agent投研, 多智能体基金, ai-hedge-fund, 投资组合, 股票池, buffett/munger/graham 视角, 回测.
---
# Hedge-Fund（多 Agent 基金投研）

把 ai-hedge-fund（多 LLM 投资者 Agent + 量化 alpha 模型）接入本地，跑一次完整的
**基金周期分析**：每个 ticker 交给多名"基金经理"（Buffett/Munger/Graham/Lynch/
Druckenmiller + PEAD 量化模型）独立给信号，再经策略混合 → 风控 → 组合 → 订单。

**数据层 = AkShare（免费、无 API key、A 股）**，不再依赖 Financial Datasets key。

红线：
- **不构成投资建议，不实盘下单**——输出是分析备忘录/回测记录
- 不编造数据：AkShare 拉不到的字段保持 None/空，绝不填充
- ticker 必须是 6 位 A 股代码（如 600519），美股代码会显式报错

## 1. 入口

```bash
# 单周期分析（默认 Financial Datasets 后端换成 AkShare）
set AIHF_DATA_PROVIDER=akshare
set PYTHONPATH=<ai-hedge-fund 路径>
python hedge_fund\run.py hedge_fund\fund\a-share-pead.yaml --tickers 600519,000858 --date 2025-06-10 --out cycle.json

# 回测（按 mandate 的 rebalance 节奏循环跑 run_cycle）
python hedge_fund\run.py <mandate.yaml> --tickers 600519 --backtest --date 2025-06-10 --out bt.json
```

## 2. 数据源选择

`AIHF_DATA_PROVIDER` 环境变量：
- `akshare` → AkShareClient（免费，A 股，新浪/东财/同花顺/百度估值）
- 缺省 → FDClient（Financial Datasets，需要 `FINANCIAL_DATASETS_API_KEY`）

AkShare 源健壮性（实测）：
- 行情 `stock_zh_a_daily`（新浪）主源 + `stock_zh_a_hist`（东财）备源，自动降级
- 财务摘要 `stock_financial_abstract_ths`（同花顺，返回**全部公开报告期**，newest-first，
  满足基本面经理 ≥4 期历史需求；point-in-time 按报告期 + 45 天披露滞后过滤）
- 估值 `stock_zh_valuation_baidu`（百度，按 end_date 取时点值）
- 所有调用 3 次重试 + 退避；`get_company_facts` 失败降级 None 不中断

> ⚠️ **回测前视警告**：披露滞后用固定的 45 天近似（季报 ~6 周够用，**年报实际可达
> 4 个月**）。`--backtest` 跑历史日期时，年报报告期可能被过早纳入。回测结果定位为
> **流程完整性验证**（无泄漏审计 + 可复现），**不作为实盘依据**。

## 3. 策略与 Agent

mandate YAML = 基金契约（策略/Agent/风控/资金/节奏），tickers 是运行输入。
- `fundamental-ls.yaml`：Buffett/Munger/Graham/Lynch/Druckenmiller 多空（需 LLM key）
- `earnings-drift.yaml`：PEAD 量化模型（纯 Python，无需 LLM key）
- `deep-value.yaml` / `inflections.yaml`：见 `hedge_fund/strategies/`

> ⚠️ **PEAD 仅限 FD 后端**：PEAD 依赖 earnings 历史（`get_earnings_history`），
> AkShare 免费接口无此数据 → **PEAD 在 AkShare 后端永远弃权（输出 0）**。
> 需 AkShare 纯量化信号请用 `a-share-backtest.yaml`（momentum+value，免 LLM key）。

## 4. 与主 Agent 协同（任务契约）

经 gate_bridge / solve_task 调用时，goal 写清楚 ticker + as_of + 期望产出，例如：

```
goal: 对 600519,000858 用 ai-hedge-fund 做多 Agent 基金分析（deep-value 策略），as_of 2025-06-10
constraints: 数据源用 AkShare（AIHF_DATA_PROVIDER=akshare）；输出 cycle.json 证据
```

产出证据（run.json / cycle.json）可回流 submit_check 验收。
