import unittest

from price_hunter.engine import CostRule, analyze_arbitrage, market_stats
from price_hunter.parser import parse_xianyu_text


class EngineTests(unittest.TestCase):
    def test_market_stats_median(self):
        stats = market_stats([10, 20, 30, 40])
        self.assertEqual(stats["median"], 25)
        self.assertEqual(stats["p25"], 17.5)

    def test_arbitrage_uses_uncapped_xianyu_fee(self):
        result = analyze_arbitrage(
            buy_price=4399,
            market_prices=[4699, 4799, 4899, 4750, 4599],
            rule=CostRule(xianyu_fee_rate=0.006, shipping=18, packaging=8, bargain_rate=0.02),
        )
        self.assertGreater(result["xianyu_fee"], 0)
        self.assertEqual(
            round(result["xianyu_fee"], 2),
            round(result["estimated_resale_price"] * 0.006, 2),
        )

    def test_parse_xianyu_text_filters_excludes(self):
        text = """
        七彩虹 RTX5070 战斧豪华版 全新未拆
        ¥4799
        七彩虹 RTX5070 Ti 战斧
        ¥5999
        """
        samples = parse_xianyu_text(text, include=["5070", "战斧"], exclude=["5070ti", "5070 ti"])
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["price"], 4799)


if __name__ == "__main__":
    unittest.main()
