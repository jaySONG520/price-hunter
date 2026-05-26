from __future__ import annotations

import json
import mimetypes
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .db import Database, ROOT
from .engine import CostRule, analyze_arbitrage
from .parser import parse_xianyu_text
from .platforms import search_links


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
        payload = self.read_json()
        try:
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
            products = self.db.list_products()
            payload = []
            for product in products:
                samples = self.db.list_samples(product["id"])
                payload.append({
                    "product": product,
                    "samples": samples,
                    "analysis": self.analysis(product, samples),
                    "links": search_links(" ".join(product["include_keywords"]) or product["name"]),
                })
            self.send_json({"products": payload})
            return

        if path == "/api/search-links":
            term = query.get("q", [""])[0]
            self.send_json({"links": search_links(term)})
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
        raw = self.rfile.read(length).decode("utf-8")
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
