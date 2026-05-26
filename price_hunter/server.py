from __future__ import annotations

import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import load_config, public_config_status
from .db import Database, ROOT
from .engine import CostRule, analyze_arbitrage
from .jd import JDUnionClient, JDUnionConfig, extract_goods_items, unwrap_jd_response
from .no_key import parse_offer_text
from .parser import parse_xianyu_text
from .platforms import history_links, search_links


WEB_ROOT = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8765


class PriceHunterHandler(BaseHTTPRequestHandler):
    db = Database()

    def log_message(self, format: str, *args) -> None:
        print(f"[server] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            self.handle_api_post(parsed.path, payload)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/products/"):
                product_id = int(parsed.path.rsplit("/", 1)[-1])
                self.db.delete_product(product_id)
                self.send_json({"ok": True})
                return
            if parsed.path.startswith("/api/samples/"):
                sample_id = int(parsed.path.rsplit("/", 1)[-1])
                self.db.delete_sample(sample_id)
                self.send_json({"ok": True})
                return
            self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_api_get(self, path: str, query: dict) -> None:
        if path == "/api/state":
            config = load_config()
            products = self.db.list_products()
            payload = []
            for product in products:
                samples = self.db.list_samples(product["id"])
                payload.append({
                    "product": product,
                    "samples": samples,
                    "analysis": self.analysis(product, samples),
                    "links": search_links(" ".join(product["include_keywords"]) or product["name"]),
                    "history_links": history_links(product["buy_url"] or product["name"]),
                })
            self.send_json({"products": payload, "config": public_config_status(config)})
            return

        if path == "/api/config/status":
            self.send_json(public_config_status(load_config()))
            return

        if path == "/api/search-links":
            term = query.get("q", [""])[0]
            self.send_json({"links": search_links(term)})
            return

        if path == "/api/history-links":
            term = query.get("q", [""])[0]
            self.send_json({"links": history_links(term)})
            return

        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def handle_api_post(self, path: str, payload: dict) -> None:
        if path == "/api/products":
            product = self.db.create_product(payload)
            self.send_json({"product": product})
            return

        if path == "/api/samples":
            sample = self.db.add_sample(payload)
            self.send_json({"sample": sample})
            return

        if path == "/api/xianyu/import":
            product = self.db.get_product(int(payload["product_id"]))
            parsed = parse_xianyu_text(
                payload.get("text", ""),
                include=product["include_keywords"],
                exclude=product["exclude_keywords"],
            )
            samples = [
                {
                    "product_id": product["id"],
                    "platform": "xianyu",
                    "title": item["title"],
                    "price": item["price"],
                    "condition": item["condition"],
                }
                for item in parsed
            ]
            created = self.db.add_samples(samples)
            self.send_json({"created": created, "count": len(created)})
            return

        if path == "/api/no-key/parse":
            offers = parse_offer_text(
                text=payload.get("text", ""),
                platform=payload.get("platform", "manual"),
                include=payload.get("include_keywords") or [],
                exclude=payload.get("exclude_keywords") or ["二手", "维修", "配件", "定金", "订金"],
            )
            self.send_json({"items": offers, "count": len(offers)})
            return

        if path == "/api/no-key/import":
            item = payload.get("item") or {}
            title = item.get("title") or item.get("name") or ""
            if not title:
                raise ValueError("缺少商品标题，不能导入。")
            product = self.db.create_product({
                "name": title,
                "category": "电子数码",
                "buy_price": float(item.get("price") or item.get("buy_price") or 0),
                "buy_url": item.get("source_url") or "",
                "include_keywords": self.keywords_from_name(title),
                "exclude_keywords": ["二手", "维修", "配件", "定金", "订金", "整机"],
                "shipping": float(payload.get("shipping") or 18),
                "packaging": float(payload.get("packaging") or 6),
                "bargain_rate": 0.02,
                "min_profit_rate": 0.06,
                "min_profit_amount": 200,
            })
            self.send_json({"product": product})
            return

        if path == "/api/jd/search":
            client = self.jd_client()
            raw = client.search_goods(
                keyword=payload.get("keyword", "").strip(),
                page_index=int(payload.get("page_index") or 1),
                page_size=int(payload.get("page_size") or 20),
                cid1=payload.get("cid1"),
                cid2=payload.get("cid2"),
                cid3=payload.get("cid3"),
                owner=payload.get("owner"),
                isCoupon=payload.get("is_coupon"),
                sortName=payload.get("sort_name") or "price",
                sort=payload.get("sort") or "asc",
            )
            self.send_json({"items": extract_goods_items(raw), "raw": unwrap_jd_response(raw)})
            return

        if path == "/api/jd/jingfen":
            client = self.jd_client()
            raw = client.jingfen_query(
                elite_id=int(payload.get("elite_id") or 24),
                page_index=int(payload.get("page_index") or 1),
                page_size=int(payload.get("page_size") or 20),
            )
            self.send_json({"items": extract_goods_items(raw), "raw": unwrap_jd_response(raw)})
            return

        if path == "/api/jd/rank":
            client = self.jd_client()
            raw = client.rank_query(
                rank_id=int(payload.get("rank_id") or 200006),
                sort_type=int(payload.get("sort_type") or 3),
                page_index=int(payload.get("page_index") or 1),
                page_size=int(payload.get("page_size") or 10),
            )
            self.send_json({"items": extract_goods_items(raw), "raw": unwrap_jd_response(raw)})
            return

        if path == "/api/jd/promotion":
            client = self.jd_client()
            raw = client.promotion_common_get(
                material_id=payload.get("material_id", "").strip(),
                coupon_url=payload.get("coupon_url", "").strip() or None,
                site_id=payload.get("site_id", "").strip() or None,
                position_id=payload.get("position_id", "").strip() or None,
            )
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/bigfield":
            client = self.jd_client()
            raw = client.goods_bigfield(
                sku_ids=payload.get("sku_ids") or [],
                fields=payload.get("fields") or ["categoryInfo", "imageInfo", "baseBigFieldInfo"],
                scene_id=int(payload.get("scene_id") or 2),
            )
            self.send_json({"items": extract_goods_items(raw), "raw": unwrap_jd_response(raw)})
            return

        if path == "/api/jd/coupon":
            client = self.jd_client()
            raw = client.coupon_query(payload.get("coupon_urls") or [])
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/category":
            client = self.jd_client()
            raw = client.category_goods_get(
                parent_id=int(payload.get("parent_id") or 0),
                grade=int(payload.get("grade") or 0),
            )
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/pid":
            client = self.jd_client()
            raw = client.user_pid_get(
                union_id=payload.get("union_id"),
                child_union_id=payload.get("child_union_id"),
            )
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/position/query":
            client = self.jd_client()
            raw = client.position_query(
                union_id=payload.get("union_id"),
                key=payload.get("key"),
                pageIndex=payload.get("page_index"),
                pageSize=payload.get("page_size"),
            )
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/position/create":
            client = self.jd_client()
            raw = client.position_create(
                union_id=payload.get("union_id"),
                key=payload.get("key"),
                positionType=payload.get("position_type"),
                spaceNameList=payload.get("space_name_list"),
            )
            self.send_json({"result": unwrap_jd_response(raw), "raw": raw})
            return

        if path == "/api/jd/import":
            item = payload.get("item") or {}
            name = item.get("name") or payload.get("name") or ""
            if not name:
                raise ValueError("京东商品缺少名称，不能导入。")
            product = self.db.create_product({
                "name": name,
                "category": "电子数码",
                "buy_price": float(item.get("buy_price") or item.get("coupon_price") or item.get("price") or 0),
                "buy_url": item.get("material_url") or "",
                "include_keywords": self.keywords_from_name(name),
                "exclude_keywords": ["二手", "维修", "配件", "整机"],
                "shipping": 18,
                "packaging": 6,
                "bargain_rate": 0.02,
                "min_profit_rate": 0.06,
                "min_profit_amount": 200,
            })
            self.send_json({"product": product})
            return

        if path == "/api/open":
            url = payload.get("url", "")
            if not url.startswith(("http://", "https://")):
                raise ValueError("Only http/https URLs can be opened")
            webbrowser.open(url)
            self.send_json({"ok": True})
            return

        if path == "/api/demo":
            self.create_demo()
            self.send_json({"ok": True})
            return

        self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def jd_client(self) -> JDUnionClient:
        jd_config = load_config().get("platforms", {}).get("jd", {})
        return JDUnionClient(JDUnionConfig.from_mapping(jd_config))

    @staticmethod
    def keywords_from_name(name: str) -> list[str]:
        words = []
        for token in name.replace("/", " ").replace("-", " ").split():
            token = token.strip()
            if len(token) >= 2 and token not in words:
                words.append(token)
        return words[:6]

    def analysis(self, product: dict, samples: list[dict]) -> dict:
        rule = CostRule(
            shipping=float(product["shipping"]),
            packaging=float(product["packaging"]),
            bargain_rate=float(product["bargain_rate"]),
            min_profit_rate=float(product["min_profit_rate"]),
            min_profit_amount=float(product["min_profit_amount"]),
        )
        return analyze_arbitrage(
            buy_price=float(product["buy_price"]),
            market_prices=[float(sample["price"]) for sample in samples],
            rule=rule,
        )

    def create_demo(self) -> None:
        product = self.db.create_product({
            "name": "七彩虹 RTX 5070 战斧豪华版 12GB",
            "category": "电子数码 / 显卡",
            "buy_price": 4399,
            "buy_url": "https://search.jd.com/Search?keyword=5070%20%E6%88%98%E6%96%A7",
            "include_keywords": ["5070", "战斧"],
            "exclude_keywords": ["5070ti", "5070 ti", "5060", "5080", "整机"],
            "shipping": 18,
            "packaging": 8,
            "bargain_rate": 0.02,
            "min_profit_rate": 0.06,
            "min_profit_amount": 260,
        })
        demo_prices = [
            ("全新未拆 七彩虹 RTX5070 战斧豪华版 国行带发票", 4799),
            ("七彩虹 5070 战斧 全新未开封 支持个人送保", 4699),
            ("RTX 5070 战斧豪华版 12G 全新", 4888),
            ("全新 5070 战斧 国行 三年保", 4750),
            ("七彩虹战斧 5070 仅拆封未使用", 4599),
            ("RTX5070 战斧 全新现货", 4899),
        ]
        for title, price in demo_prices:
            self.db.add_sample({
                "product_id": product["id"],
                "platform": "xianyu",
                "title": title,
                "price": price,
                "condition": "全新",
            })

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            path = "/index.html"
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        data = self.rfile.read(length)
        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                raw = data.decode("gb18030")
            except UnicodeDecodeError:
                raw = data.decode("utf-8", errors="replace")
        return json.loads(raw)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), PriceHunterHandler)
    print(f"Price Hunter running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
