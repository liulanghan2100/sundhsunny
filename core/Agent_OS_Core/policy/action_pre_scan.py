"""Deterministic action discovery before risk classification.

LLM output may contribute actions, but it can never remove actions found by
this scanner. The result is intentionally conservative.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# 词表扩充说明（agentos-hub）：
# 原表只覆盖浅层动词，实测 "drop table users" / "转账100万" / "清空数据库"
# 均判为 L1（无需审批）。这与本模块 docstring 所述「conservative」原则相悖，
# 故按「不可逆 / 涉钱 / 涉隐私 / 涉库表 / 对外」五类补齐。
ACTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "delete": (
        "delete", "remove", "rm ", "del ", "drop ", "drop table", "truncate",
        "purge", "wipe", "删除", "移除", "清空", "清除", "抹除", "卸载",
        "格式化", "销毁", "批量删",
        # 补：口语单字与变体（原表漏收，实测"把 x 删掉"判成了无动作）
        "删掉", "删了", "删除掉", "干掉", "废掉", "去掉",
    ),
    "move": ("move", "rename", "mv ", "移动", "重命名", "迁移文件"),
    "write": (
        "write", "edit", "modify", "patch", "update ", "overwrite", "insert into",
        "写入", "修改", "编辑", "覆盖", "更新", "改写",
        # 补：原表只收双字词，漏了口语里更常用的单字与变体。
        # 实测"改一下 hub.py"命中不了任何动作 -> 判成 L1（应为 L2）。
        # 单字"改"最口语也最常见；误伤面（改进/改善/改正）在任务描述里
        # 出现率低，且误判方向是升高风险，代价仅多一步确认。
        "改",
        "改一下", "改改", "改掉", "改动", "改一改",
        "替换", "换掉", "调整", "改动一下", "修改一下",
        "重写", "refactor", "重命名变量",
    ),
    "provider_api": (
        "provider", "api call", "api调用", "真实接口", "模型调用", "调用模型",
        "外部接口",
    ),
    "network": (
        "network", "http://", "https://", "upload", "download", "fetch",
        "联网", "网络", "抓取", "上传", "下载", "爬取", "外网", "公网",
    ),
    "sandbox": ("sandbox", "沙箱"),
    "publish": (
        "publish", "deploy", "release", "rollout", "go live",
        "发布", "部署", "上线", "投放", "对外发布", "推送到生产",
    ),
    "credentials": (
        "credential", "secret", "token", "password", "passwd", "private key",
        "api key", "身份证", "银行卡", "密钥", "密码", "凭据", "令牌", "私钥",
        "信用卡", "证件号", "手机号", "个人信息", "隐私数据",
    ),
    "runtime_dispatch": (
        "runtime", "dispatch", "execute task", "执行任务", "调度", "触发任务",
    ),
    "registry_writeback": (
        "registry", "status writeback", "skill writeback", "writeback",
        "注册表", "状态回写", "写回",
    ),
    "external_write": (
        "send", "email", "webhook", "external write", "sms", "notify",
        "外部写入", "发送", "邮件", "短信", "通知", "推送消息", "群发",
    ),
    # 新增：资金与交易。原表缺失，导致「转账100万」判为 L1。
    "financial": (
        "transfer", "withdraw", "payment", "purchase", "order", "trade",
        "转账", "汇款", "付款", "支付", "提现", "充值", "下单", "购买",
        "交易", "打款", "退款", "划转", "金额",
    ),
    # 新增：隐私与敏感数据读取。原表缺失，导致「读取信用卡信息」判为 L1。
    "sensitive_read": (
        "read credit", "dump data", "export all", "extract data", "scrape",
        "读取身份证", "导出数据", "批量导出", "导出全部", "读取隐私",
        "导出客户", "导出用户", "拉取数据",
    ),
}


@dataclass(frozen=True)
class ActionScanResult:
    requested_actions: tuple[str, ...]
    lexical_actions: tuple[str, ...]
    effective_actions: tuple[str, ...]
    disagreements: tuple[str, ...]
    matched_terms: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_actions": list(self.requested_actions),
            "lexical_actions": list(self.lexical_actions),
            "effective_actions": list(self.effective_actions),
            "disagreements": list(self.disagreements),
            "matched_terms": {key: list(value) for key, value in self.matched_terms.items()},
        }


def scan_requested_actions(
    request_text: str,
    *,
    llm_actions: list[str] | tuple[str, ...] | None = None,
    context: dict[str, Any] | None = None,
) -> ActionScanResult:
    text = f"{request_text} {context or {}}".lower()
    requested = {str(item).strip().lower() for item in (llm_actions or ()) if str(item).strip()}
    lexical: set[str] = set()
    matched: dict[str, tuple[str, ...]] = {}
    for action, patterns in ACTION_PATTERNS.items():
        hits = tuple(pattern for pattern in patterns if pattern.lower() in text)
        if hits:
            lexical.add(action)
            matched[action] = hits
    effective = requested | lexical
    disagreements = tuple(sorted(lexical - requested))
    return ActionScanResult(
        requested_actions=tuple(sorted(requested)),
        lexical_actions=tuple(sorted(lexical)),
        effective_actions=tuple(sorted(effective)),
        disagreements=disagreements,
        matched_terms=matched,
    )
