# -*- coding: utf-8 -*-
"""Pure helpers for GAIA budget estimation."""
import json
from datetime import datetime, timezone


LEVEL_TOTAL = {1: 146, 2: 245, 3: 75}
LEVEL_SPLIT = {
    "validation": {1: 53, 2: 86, 3: 26},
    "test": {1: 93, 2: 159, 3: 49},
}
PRICE_INPUT_MISS = 1.0
PRICE_INPUT_HIT = 0.02
PRICE_OUTPUT = 2.0
PER_LEVEL = {
    1: {"avg_calls": 2.0, "avg_input_k": 2.0, "avg_output_k": 0.4},
    2: {"avg_calls": 3.5, "avg_input_k": 4.0, "avg_output_k": 0.6},
    3: {"avg_calls": 5.0, "avg_input_k": 6.0, "avg_output_k": 0.8},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_payload(cache_hit: float, peak_factor: float = 1.0) -> dict:
    rows = []
    totals = {"questions": 0, "calls": 0, "input_m": 0.0, "output_m": 0.0, "input_miss_m": 0.0, "input_hit_m": 0.0}
    for level in (1, 2, 3):
        n = LEVEL_TOTAL[level]
        m = PER_LEVEL[level]
        calls = n * m["avg_calls"]
        input_m = n * m["avg_calls"] * m["avg_input_k"] / 1000.0
        output_m = n * m["avg_calls"] * m["avg_output_k"] / 1000.0
        input_miss_m = input_m * (1.0 - cache_hit)
        input_hit_m = input_m * cache_hit
        cost_miss = input_miss_m * PRICE_INPUT_MISS
        cost_hit = input_hit_m * PRICE_INPUT_HIT
        cost_output = output_m * PRICE_OUTPUT
        cost = (cost_miss + cost_hit + cost_output) * peak_factor
        rows.append({
            "level": level,
            "questions": n,
            "avg_calls": m["avg_calls"],
            "total_calls": round(calls, 1),
            "input_m": round(input_m, 3),
            "output_m": round(output_m, 3),
            "input_miss_m": round(input_miss_m, 3),
            "input_hit_m": round(input_hit_m, 3),
            "cost_cny_offpeak": round(cost / peak_factor, 2),
            "cost_cny_peak": round(cost, 2),
        })
        totals["questions"] += n
        totals["calls"] += calls
        totals["input_m"] += input_m
        totals["output_m"] += output_m
        totals["input_miss_m"] += input_miss_m
        totals["input_hit_m"] += input_hit_m
    totals_cost = (totals["input_miss_m"] * PRICE_INPUT_MISS + totals["input_hit_m"] * PRICE_INPUT_HIT + totals["output_m"] * PRICE_OUTPUT)
    return {
        "schema_version": "agent-os-gaia-budget/v0.1",
        "generated": now(),
        "assumptions": {
            "cache_hit": cache_hit,
            "peak_factor": peak_factor,
            "price_input_miss_cny_per_m": PRICE_INPUT_MISS,
            "price_input_hit_cny_per_m": PRICE_INPUT_HIT,
            "price_output_cny_per_m": PRICE_OUTPUT,
            "per_level": PER_LEVEL,
        },
        "distribution": LEVEL_TOTAL,
        "split_distribution": LEVEL_SPLIT,
        "by_level": rows,
        "totals": {
            "questions": totals["questions"],
            "calls": round(totals["calls"], 1),
            "input_m": round(totals["input_m"], 3),
            "output_m": round(totals["output_m"], 3),
            "total_m": round(totals["input_m"] + totals["output_m"], 3),
            "input_miss_m": round(totals["input_miss_m"], 3),
            "input_hit_m": round(totals["input_hit_m"], 3),
            "cost_cny_offpeak": round(totals_cost, 2),
            "cost_cny_peak": round(totals_cost * peak_factor, 2),
        },
    }


def render_markdown(result: dict) -> str:
    t = result["totals"]
    lines = [
        "# GAIA 466 题 DeepSeek 预算预估明细",
        "",
        f"生成时间: {result['generated']}",
        "",
        "## 一、预估模型假设",
        "",
        "- 求解器: `agent_os_gaia_runner.py`(ReAct 循环,MAX_STEPS=5)",
        "- 模型: DeepSeek V4-Flash(即 deepseek-chat 非思考模式)",
        f"- 输入(缓存未命中): ¥{result['assumptions']['price_input_miss_cny_per_m']}/M",
        f"- 输入(缓存命中): ¥{result['assumptions']['price_input_hit_cny_per_m']}/M",
        f"- 输出: ¥{result['assumptions']['price_output_cny_per_m']}/M",
        f"- 缓存命中率假设: {result['assumptions']['cache_hit']:.0%}",
        "- 高峰期(工作日 9-12/14-18)价格翻倍",
        "",
        "## 二、题量分布(官方核实)",
        "",
        "| Level | validation | test | 合计 |",
        "|---|---:|---:|---:|",
    ]
    d = result["split_distribution"]
    for level in (1, 2, 3):
        lines.append(f"| L{level} | {d['validation'][level]} | {d['test'][level]} | {result['distribution'][level]} |")
    lines += [
        f"| 合计 | {sum(d['validation'].values())} | {sum(d['test'].values())} | {result['distribution'][1] + result['distribution'][2] + result['distribution'][3]} |",
        "",
        "## 三、调用次数与 Token 消耗分布",
        "",
        "| Level | 题数 | 平均调用/题 | 总调用次数 | 输入(M) | 输出(M) | 合计(M) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["by_level"]:
        total_m = row["input_m"] + row["output_m"]
        lines.append(f"| L{row['level']} | {row['questions']} | {row['avg_calls']} | {row['total_calls']:.0f} | {row['input_m']:.2f} | {row['output_m']:.2f} | {total_m:.2f} |")
    lines += [
        f"| 合计 | {t['questions']} | — | {t['calls']:.0f} | {t['input_m']:.2f} | {t['output_m']:.2f} | {t['total_m']:.2f} |",
        "",
        "## 四、费用估算",
        "",
        "| Level | 费用-平时(¥) | 费用-高峰(¥) |",
        "|---|---:|---:|",
    ]
    for row in result["by_level"]:
        lines.append(f"| L{row['level']} | {row['cost_cny_offpeak']:.2f} | {row['cost_cny_peak']:.2f} |")
    lines += [
        f"| **合计** | **{t['cost_cny_offpeak']:.2f}** | **{t['cost_cny_peak']:.2f}** |",
        "",
        "## 五、结论",
        "",
        f"全量 466 题预计 **{t['calls']:.0f} 次 API 调用**、消耗约 **{t['total_m']:.1f}M tokens**,"
        f"平时费用约 **¥{t['cost_cny_offpeak']:.2f}**,高峰约 **¥{t['cost_cny_peak']:.2f}**。",
        "",
        "> 注: L3 长链任务(token 消耗波动最大),建议预留 2-3 倍余量。",
        "> 预算帽(gaia_eval_binding)已设 ¥60,充足覆盖。",
        "",
    ]
    return "\n".join(lines)
