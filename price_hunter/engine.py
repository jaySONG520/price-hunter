from __future__ import annotations

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class CostRule:
    xianyu_fee_rate: float = 0.006
    shipping: float = 18.0
    packaging: float = 6.0
    bargain_rate: float = 0.02
    min_profit_rate: float = 0.06
    min_profit_amount: float = 200.0


def percentile(values: list[float], point: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * point
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def trimmed_mean(values: list[float], trim_ratio: float = 0.1) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim = int(len(ordered) * trim_ratio)
    if trim and len(ordered) > trim * 2:
        ordered = ordered[trim:-trim]
    return mean(ordered)


def market_stats(prices: list[float]) -> dict:
    clean = [float(price) for price in prices if price and price > 0]
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
            "trimmed_mean": None,
        }

    ordered = sorted(clean)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p25": percentile(ordered, 0.25),
        "median": percentile(ordered, 0.5),
        "p75": percentile(ordered, 0.75),
        "max": ordered[-1],
        "trimmed_mean": trimmed_mean(ordered),
    }


def analyze_arbitrage(
    buy_price: float,
    market_prices: list[float],
    rule: CostRule | None = None,
) -> dict:
    rule = rule or CostRule()
    stats = market_stats(market_prices)
    if stats["count"] == 0 or not buy_price:
        return {
            "stats": stats,
            "estimated_resale_price": None,
            "xianyu_fee": None,
            "net_after_costs": None,
            "profit": None,
            "profit_rate": None,
            "recommendation": "DATA_WEAK",
            "reason": "缺少买入价或闲鱼样本。",
        }

    median_price = stats["median"] or 0
    estimated_resale = median_price * (1 - rule.bargain_rate)
    xianyu_fee = estimated_resale * rule.xianyu_fee_rate
    net_after_costs = estimated_resale - xianyu_fee - rule.shipping - rule.packaging
    profit = net_after_costs - buy_price
    profit_rate = profit / buy_price if buy_price else 0

    min_profit = max(rule.min_profit_amount, buy_price * rule.min_profit_rate)
    if stats["count"] < 5:
        recommendation = "DATA_WEAK"
        reason = "闲鱼样本少于 5 条，只能参考，建议继续采样。"
    elif profit >= min_profit:
        recommendation = "BUY"
        reason = "预估净利润达到最低利润要求。"
    elif profit > 0:
        recommendation = "WATCH"
        reason = "有利润但安全垫不足，适合继续观察或压低买入价。"
    else:
        recommendation = "PASS"
        reason = "扣除闲鱼成本和基础履约成本后预计亏损。"

    return {
        "stats": stats,
        "estimated_resale_price": estimated_resale,
        "xianyu_fee": xianyu_fee,
        "net_after_costs": net_after_costs,
        "profit": profit,
        "profit_rate": profit_rate,
        "recommendation": recommendation,
        "reason": reason,
        "rule": {
            "xianyu_fee_rate": rule.xianyu_fee_rate,
            "shipping": rule.shipping,
            "packaging": rule.packaging,
            "bargain_rate": rule.bargain_rate,
            "min_profit_rate": rule.min_profit_rate,
            "min_profit_amount": rule.min_profit_amount,
        },
    }
