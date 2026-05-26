import unittest

from price_hunter.engine import CostRule, analyze_arbitrage, market_stats
from price_hunter.jd import extract_goods_items, jd_timestamp, sign_params, unwrap_jd_response
from price_hunter.no_key import parse_offer_text
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

    def test_jd_timestamp_uses_gmt8_format(self):
        self.assertEqual(jd_timestamp().__len__(), 19)
        self.assertRegex(jd_timestamp(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_jd_sign_sorts_params_and_uppercases_md5(self):
        params = {
            "method": "jd.union.open.goods.query",
            "app_key": "app",
            "timestamp": "2026-05-26 12:00:00",
            "format": "json",
            "v": "1.0",
            "sign_method": "md5",
            "goodsReqDTO": '{"keyword":"5070"}',
        }
        self.assertEqual(sign_params(params, "secret"), sign_params(dict(reversed(list(params.items()))), "secret"))
        self.assertEqual(sign_params(params, "secret"), sign_params(params, "secret").upper())

    def test_jd_goods_response_normalization(self):
        raw = {
            "jd_union_open_goods_query_responce": {
                "queryResult": {
                    "code": "200",
                    "data": {
                        "goodsResp": {
                            "skuId": "123",
                            "skuName": "七彩虹 RTX 5070 战斧",
                            "materialUrl": "item.jd.com/123.html",
                            "priceInfo": {"price": "4599", "lowestCouponPrice": "4399"},
                            "couponInfo": {"couponList": {"coupon": {"link": "https://coupon.jd.com/x", "discount": "200"}}},
                        }
                    },
                }
            }
        }
        unwrapped = unwrap_jd_response(raw)
        self.assertEqual(unwrapped["code"], "200")
        items = extract_goods_items(raw)
        self.assertEqual(items[0]["sku_id"], "123")
        self.assertEqual(items[0]["buy_price"], 4399)
        self.assertEqual(items[0]["coupon_discount"], 200)
        self.assertEqual(items[0]["material_url"], "https://item.jd.com/123.html")

    def test_no_key_parser_reads_visible_offer_text(self):
        text = """
        七彩虹 RTX 5070 战斧豪华版 12GB 显卡
        ¥4399
        RTX 5070 战斧 配件支架
        ¥99
        """
        offers = parse_offer_text(text, platform="jd", include=["5070", "战斧"], exclude=["配件"])
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["price"], 4399)
        self.assertEqual(offers[0]["platform"], "jd")


if __name__ == "__main__":
    unittest.main()
