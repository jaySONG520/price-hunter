from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "price_hunter.sqlite"


class Database:
    def __init__(self, path: Path = DB_PATH):
        DATA_DIR.mkdir(exist_ok=True)
        self.path = path
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '电子数码',
                    buy_price REAL NOT NULL DEFAULT 0,
                    buy_url TEXT NOT NULL DEFAULT '',
                    include_keywords TEXT NOT NULL DEFAULT '[]',
                    exclude_keywords TEXT NOT NULL DEFAULT '[]',
                    shipping REAL NOT NULL DEFAULT 18,
                    packaging REAL NOT NULL DEFAULT 6,
                    bargain_rate REAL NOT NULL DEFAULT 0.02,
                    min_profit_rate REAL NOT NULL DEFAULT 0.06,
                    min_profit_amount REAL NOT NULL DEFAULT 200,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'xianyu',
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    condition TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
                );
                """
            )

    def create_product(self, payload: dict) -> dict:
        now = time()
        include = payload.get("include_keywords") or []
        exclude = payload.get("exclude_keywords") or []
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO products (
                    name, category, buy_price, buy_url, include_keywords, exclude_keywords,
                    shipping, packaging, bargain_rate, min_profit_rate, min_profit_amount, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("name", "").strip(),
                    payload.get("category", "电子数码").strip() or "电子数码",
                    float(payload.get("buy_price") or 0),
                    payload.get("buy_url", "").strip(),
                    json.dumps(include, ensure_ascii=False),
                    json.dumps(exclude, ensure_ascii=False),
                    float(payload.get("shipping") or 18),
                    float(payload.get("packaging") or 6),
                    float(payload.get("bargain_rate") or 0.02),
                    float(payload.get("min_profit_rate") or 0.06),
                    float(payload.get("min_profit_amount") or 200),
                    now,
                ),
            )
            conn.commit()
            return self.get_product(cur.lastrowid)

    def list_products(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
            return [self._product(row) for row in rows]

    def get_product(self, product_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row:
                raise KeyError(f"Product {product_id} not found")
            return self._product(row)

    def delete_product(self, product_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()

    def add_sample(self, payload: dict) -> dict:
        now = time()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO samples (product_id, platform, title, price, condition, source_url, location, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(payload["product_id"]),
                    payload.get("platform", "xianyu"),
                    payload.get("title", "").strip(),
                    float(payload.get("price") or 0),
                    payload.get("condition", "").strip(),
                    payload.get("source_url", "").strip(),
                    payload.get("location", "").strip(),
                    now,
                ),
            )
            conn.commit()
            return self.get_sample(cur.lastrowid)

    def add_samples(self, samples: list[dict]) -> list[dict]:
        return [self.add_sample(sample) for sample in samples if sample.get("title") and sample.get("price")]

    def get_sample(self, sample_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
            if not row:
                raise KeyError(f"Sample {sample_id} not found")
            return dict(row)

    def list_samples(self, product_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM samples WHERE product_id = ? ORDER BY id DESC",
                (product_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_sample(self, sample_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
            conn.commit()

    @staticmethod
    def _product(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["include_keywords"] = json.loads(data["include_keywords"] or "[]")
        data["exclude_keywords"] = json.loads(data["exclude_keywords"] or "[]")
        return data
