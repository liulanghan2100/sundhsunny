# -*- coding: utf-8 -*-
"""research 技能的一手财报数据抓取工具。

自动抓取公司一手财报数据，输出标准化「事实包」Markdown（可直接作为 debate-protocol 第 1 步输入）。

数据源（均为一手/接近一手）：
- A股：AkShare（东财接口，三大报表/财务摘要/财务指标）
- 美股：SEC EDGAR XBRL（companyfacts API，公司向 SEC 申报的结构化财务数据）

用法：
  python financial_data.py A 600519            # A股：财务摘要 + 近三年财务指标
  python financial_data.py A 600519 --balance  # A股：加抓三大报表（资产负债表/利润表/现金流）
  python financial_data.py US AAPL             # 美股：EDGAR 公司事实（营收/净利润/资产/负债/现金流）
  python financial_data.py US AAPL --filings   # 美股：列出最近 10-K/10-Q 申报文件链接

输出：写 Markdown 到 research 技能目录 facts/<symbol>_<date>.md，并打印路径。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent / "facts"
SEC_UA = "research-financial-data/1.0 (contact@example.com)"


def _md_table(rows: list[list[str]], headers: list[str]) -> str:
    """把行数据渲染成 GitHub 风格 Markdown 表。"""
    if not rows:
        return "_（无数据）_"
    cols = max(len(headers), max(len(r) for r in rows))
    rows = [r + [""] * (cols - len(r)) for r in rows]
    headers = headers + [""] * (cols - len(headers))
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


# ---------- A 股（AkShare） ----------

def fetch_a_share(symbol: str, with_statements: bool = False) -> str:
    import akshare as ak  # 延迟导入：仅 A 股路径需要

    parts = [f"# {symbol} 财务事实包（A股，AkShare/东财）", "",
             f"> 抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 数据源：东方财富（AkShare 1.x）", ""]

    # 基本信息
    try:
        info = ak.stock_individual_info_em(symbol=symbol)
        rows = [[r["item"], r["value"]] for _, r in info.iterrows()]
        parts += ["## 公司信息", _md_table(rows, ["项目", "内容"]), ""]
    except Exception as e:  # noqa: BLE001
        parts.append(f"## 公司信息\n\n_抓取失败: {e}_\n")

    # 财务摘要（营收/净利润/毛利/现金流/ROE 等）
    try:
        abstract = ak.stock_financial_abstract(symbol=symbol)
        # 列结构: ['选项'(分组), '指标'(指标名), <各报告期>...]
        date_cols = [c for c in abstract.columns if c not in ("选项", "指标")][:4]
        cols = ["指标"] + [str(c) for c in date_cols]
        rows = [[str(r["指标"]).strip()] + [str(r[c]) for c in date_cols]
                for _, r in abstract.head(25).iterrows()]
        parts += ["## 财务摘要（最近报告期）", _md_table(rows, cols), ""]
    except Exception as e:  # noqa: BLE001
        parts.append(f"## 财务摘要\n\n_抓取失败: {e}_\n")

    # 财务指标（含 ROE/负债率/现金流等）
    try:
        ind = ak.stock_financial_analysis_indicator(symbol=symbol, start_year=str(date.today().year - 3))
        cols = list(ind.columns[:2]) + list(ind.columns[2:8])
        rows = [[str(r[c]) for c in cols] for _, r in ind.head(8).iterrows()]
        parts += ["## 财务指标（近 3 年）", _md_table(rows, [str(c) for c in cols]), ""]
    except Exception as e:  # noqa: BLE001
        parts.append(f"## 财务指标\n\n_抓取失败: {e}_\n")

    # 三大报表（可选）
    if with_statements:
        for name, func in [("资产负债表", ak.stock_balance_sheet_by_yearly_em),
                           ("利润表", ak.stock_profit_sheet_by_yearly_em),
                           ("现金流量表", ak.stock_cash_flow_sheet_by_yearly_em)]:
            try:
                df = func(symbol=symbol)
                cols = list(df.columns[:2]) + list(df.columns[2:6])
                rows = [[str(r[c]) for c in cols] for _, r in df.head(15).iterrows()]
                parts += [f"## {name}（年度，近 4 期）", _md_table(rows, [str(c) for c in cols]), ""]
            except Exception as e:  # noqa: BLE001
                parts.append(f"## {name}\n\n_抓取失败: {e}_\n")

    return "\n".join(parts)


# ---------- 美股（SEC EDGAR XBRL） ----------

def _cik_from_ticker(ticker: str) -> str | None:
    """通过 EDGAR tickers 映射查 CIK。"""
    url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(url, headers={"User-Agent": SEC_UA}, timeout=30)
    r.raise_for_status()
    for v in r.json().values():
        if v["ticker"].upper() == ticker.upper():
            return str(v["cik_str"]).zfill(10)
    return None


def _gaap_value(facts: dict, tags: list[str], max_rows: int = 5) -> list[list[str]]:
    """从 companyfacts JSON 提取指定 GAAP 标签的年度值（USD 千元）。

    tags 支持备选标签（公司可能切换 GAAP 标签名）；fp=='FY' 表示财年值，
    form 是 '10-K'/'10-Q' 等申报表单（不做过滤条件）。按期末日去重。
    """
    seen: set[str] = set()
    rows: list[list[str]] = []
    for tag in tags:
        units = facts.get("us-gaap", {}).get(tag, {}).get("units", {})
        for unit, entries in units.items():  # 通常 USD
            for e in entries:
                if e.get("fp") == "FY" and e.get("end") not in seen:
                    seen.add(e.get("end"))
                    rows.append([e.get("end"), e.get("start"), f"{e.get('val', 0) / 1e6:,.1f}M"])
    if rows:
        rows.sort(key=lambda x: x[0])
        return rows[-max_rows:]
    return []


def fetch_us_edgar(ticker: str, with_filings: bool = False) -> str:
    parts = [f"# {ticker.upper()} 财务事实包（美股，SEC EDGAR XBRL）", "",
             f"> 抓取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 数据源：SEC EDGAR companyfacts（一手申报）", ""]

    cik = _cik_from_ticker(ticker)
    if not cik:
        return f"# {ticker.upper()}\n\n_未在 EDGAR tickers 映射中找到该代码_"
    parts.append(f"- **CIK**: {cik}\n")

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    r = requests.get(url, headers={"User-Agent": SEC_UA}, timeout=60)
    r.raise_for_status()
    facts = r.json().get("facts", {})

    tags = [
        (["Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"], "营收"),
        (["NetIncomeLoss"], "净利润"),
        (["OperatingIncomeLoss"], "营业利润"),
        (["Assets"], "总资产"),
        (["Liabilities"], "总负债"),
        (["StockholdersEquity"], "股东权益"),
        (["NetCashProvidedByUsedInOperatingActivities"], "经营现金流"),
    ]
    for tag_list, cn in tags:
        rows = _gaap_value(facts, tag_list)
        if rows:
            parts += [f"## {cn} 年度值", _md_table(rows, ["期末", "期初", "金额(USD)"]), ""]
        else:
            parts.append(f"## {cn}\n\n_（该报告期年度值未取到）_\n")

    if with_filings:
        try:
            sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                               headers={"User-Agent": SEC_UA}, timeout=60).json()
            recent = sub.get("filings", {}).get("recent", {})
            forms, dates, accns, docs = recent.get("form", []), recent.get("filingDate", []), recent.get("accessionNumber", []), recent.get("primaryDocument", [])
            rows = []
            for i, f in enumerate(forms):
                if f in ("10-K", "10-Q"):
                    acc = accns[i].replace("-", "")
                    rows.append([f, dates[i], f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{docs[i]}"])
                if len(rows) >= 8:
                    break
            parts += ["## 最近申报文件（10-K/10-Q）", _md_table(rows, ["表单", "日期", "链接"]), ""]
        except Exception as e:  # noqa: BLE001
            parts.append(f"## 申报文件\n\n_抓取失败: {e}_\n")

    return "\n".join(parts)


# ---------- main ----------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="一手财报数据抓取工具（research 配套）")
    parser.add_argument("market", choices=["A", "US"], help="A=AkShare(A股) / US=SEC EDGAR(美股)")
    parser.add_argument("symbol", help="A股六位代码 或 美股 Ticker")
    parser.add_argument("--balance", action="store_true", help="A股：加抓三大报表")
    parser.add_argument("--filings", action="store_true", help="美股：列出最近 10-K/10-Q 申报链接")
    args = parser.parse_args(argv)

    try:
        if args.market == "A":
            md = fetch_a_share(args.symbol, with_statements=args.balance)
        else:
            md = fetch_us_edgar(args.symbol.upper(), with_filings=args.filings)
    except Exception as e:  # noqa: BLE001
        print(f"抓取失败: {e}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.market}_{args.symbol}_{date.today().isoformat()}.md"
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n>>> 事实包已写入: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
