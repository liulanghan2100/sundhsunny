"""Hard cost budget guard. It never auto-switches providers or models."""
from __future__ import annotations


class CostBudgetExceeded(RuntimeError):
    pass


class CostBudgetGuard:
    def __init__(self, budget_usd: float) -> None:
        if budget_usd < 0:
            raise ValueError("budget_usd cannot be negative")
        self.budget_usd = float(budget_usd)
        self.reserved_usd = 0.0
        self.actual_usd = 0.0

    def reserve(self, estimated_usd: float) -> None:
        estimated_usd = float(estimated_usd)
        if estimated_usd < 0 or self.actual_usd + self.reserved_usd + estimated_usd > self.budget_usd:
            raise CostBudgetExceeded("cost budget exceeded")
        self.reserved_usd += estimated_usd

    def settle(self, reserved_usd: float, actual_usd: float) -> None:
        self.reserved_usd = max(0.0, self.reserved_usd - float(reserved_usd))
        self.actual_usd += float(actual_usd)
        if self.actual_usd > self.budget_usd:
            raise CostBudgetExceeded("actual cost exceeded hard budget")

    def snapshot(self) -> dict[str, float]:
        return {
            "budget_usd": self.budget_usd,
            "reserved_usd": self.reserved_usd,
            "actual_usd": self.actual_usd,
            "remaining_usd": max(0.0, self.budget_usd - self.reserved_usd - self.actual_usd),
        }
