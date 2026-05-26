from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any


JD_TIMEZONE = timezone(timedelta(hours=8))


class JDConfigError(RuntimeError):
    pass


class JDAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class JDUnionConfig:
    app_key: str
    app_secret: str
    server_url: str = "https://router.jd.com/api"
    access_token: str = ""
    site_id: str = ""
    pid: str = ""
    position_id: str = ""
    union_id: str = ""
    auth_key: str = ""
    enabled: bool = False

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> "JDUnionConfig":
        return cls(
            app_key=str(mapping.get("app_key", "")).strip(),
            app_secret=str(mapping.get("app_secret", "")).strip(),
            server_url=str(mapping.get("server_url", "https://router.jd.com/api")).strip(),
            access_token=str(mapping.get("access_token", "")).strip(),
            site_id=str(mapping.get("site_id", "")).strip(),
            pid=str(mapping.get("pid", "")).strip(),
            position_id=str(mapping.get("position_id", "")).strip(),
            union_id=str(mapping.get("union_id", "")).strip(),
            auth_key=str(mapping.get("auth_key", "")).strip(),
            enabled=bool(mapping.get("enabled", False)),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.app_key and self.app_secret)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def jd_timestamp(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.astimezone(JD_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def sign_params(params: dict[str, Any], app_secret: str) -> str:
    filtered = {key: "" if value is None else str(value) for key, value in params.items() if key != "sign"}
    raw = app_secret + "".join(f"{key}{filtered[key]}" for key in sorted(filtered)) + app_secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def first_number(*values: Any) -> float | None:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def first_text(*values: Any) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def nested(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


class JDUnionClient:
    def __init__(self, config: JDUnionConfig, timeout: int = 20):
        self.config = config
        self.timeout = timeout

    def ensure_configured(self) -> None:
        if not self.config.is_configured:
            raise JDConfigError("京东 API 尚未配置。请在 config.local.json 或环境变量中填写 app_key/app_secret 并启用 jd.enabled。")

    def call(self, method: str, payload_name: str, payload: Any, version: str = "1.0") -> dict[str, Any]:
        self.ensure_configured()
        params: dict[str, Any] = {
            "method": method,
            "app_key": self.config.app_key,
            "timestamp": jd_timestamp(),
            "format": "json",
            "v": version,
            "sign_method": "md5",
        }
        if self.config.access_token:
            params["access_token"] = self.config.access_token
        if payload_name:
            params[payload_name] = json_dumps(payload)
        params["sign"] = sign_params(params, self.config.app_secret)

        body = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(
            self.config.server_url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise JDAPIError(f"京东 API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise JDAPIError(f"京东 API 网络错误: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JDAPIError(f"京东 API 返回非 JSON: {raw[:300]}") from exc

        error = data.get("error_response") or data.get("errorResponse")
        if error:
            raise JDAPIError(json_dumps(error))
        return data

    def search_goods(self, keyword: str, page_index: int = 1, page_size: int = 20, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "keyword": keyword,
            "pageIndex": page_index,
            "pageSize": min(max(page_size, 1), 30),
        }
        if self.config.pid:
            payload["pid"] = self.config.pid
        payload.update({key: value for key, value in kwargs.items() if value not in (None, "")})
        return self.call("jd.union.open.goods.query", "goodsReqDTO", payload)

    def goods_bigfield(self, sku_ids: list[int | str], fields: list[str] | None = None, scene_id: int = 2) -> dict[str, Any]:
        payload = {
            "skuIds": [int(sku) for sku in sku_ids],
            "sceneId": scene_id,
        }
        if fields:
            payload["fields"] = fields
        return self.call("jd.union.open.goods.bigfield.query", "goodsReq", payload)

    def coupon_query(self, coupon_urls: list[str]) -> dict[str, Any]:
        return self.call("jd.union.open.coupon.query", "couponUrls", coupon_urls[:50])

    def promotion_common_get(
        self,
        material_id: str,
        site_id: str | None = None,
        position_id: str | None = None,
        coupon_url: str | None = None,
        sub_union_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "materialId": material_id,
            "siteId": site_id or self.config.site_id,
        }
        if position_id or self.config.position_id:
            payload["positionId"] = position_id or self.config.position_id
        if coupon_url:
            payload["couponUrl"] = coupon_url
        if sub_union_id:
            payload["subUnionId"] = sub_union_id
        if not payload["siteId"]:
            raise JDConfigError("生成京东推广链接需要 site_id。")
        return self.call("jd.union.open.promotion.common.get", "promotionCodeReq", payload)

    def category_goods_get(self, parent_id: int = 0, grade: int = 0) -> dict[str, Any]:
        return self.call("jd.union.open.category.goods.get", "req", {"parentId": parent_id, "grade": grade})

    def user_pid_get(self, union_id: int | str | None = None, child_union_id: int | str | None = None) -> dict[str, Any]:
        payload = {"unionId": int(union_id or self.config.union_id or 0)}
        if child_union_id:
            payload["childUnionId"] = int(child_union_id)
        return self.call("jd.union.open.user.pid.get", "pidReq", payload)

    def position_create(self, union_id: int | str | None = None, key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "unionId": int(union_id or self.config.union_id or 0),
            "key": key or self.config.auth_key,
        }
        payload.update({name: value for name, value in kwargs.items() if value not in (None, "")})
        return self.call("jd.union.open.position.create", "positionReq", payload)

    def position_query(self, union_id: int | str | None = None, key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "unionId": int(union_id or self.config.union_id or 0),
            "key": key or self.config.auth_key,
        }
        payload.update({name: value for name, value in kwargs.items() if value not in (None, "")})
        return self.call("jd.union.open.position.query", "positionReq", payload)

    def jingfen_query(self, elite_id: int = 24, page_index: int = 1, page_size: int = 20) -> dict[str, Any]:
        payload = {"eliteId": elite_id, "pageIndex": page_index, "pageSize": min(max(page_size, 1), 50)}
        if self.config.pid:
            payload["pid"] = self.config.pid
        return self.call("jd.union.open.goods.jingfen.query", "goodsReq", payload)

    def rank_query(self, rank_id: int = 200006, sort_type: int = 3, page_index: int = 1, page_size: int = 10) -> dict[str, Any]:
        payload = {
            "rankId": rank_id,
            "sortType": sort_type,
            "pageIndex": page_index,
            "pageSize": min(max(page_size, 1), 20),
        }
        return self.call("jd.union.open.goods.rank.query", "rankGoodsReq", payload)


def unwrap_jd_response(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    response = next((value for key, value in data.items() if key.endswith("_responce") or key.endswith("_response")), data)
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict):
        return {"data": response}

    result = response.get("queryResult") or response.get("getResult") or response.get("result") or response
    if isinstance(result, str):
        result = json.loads(result)
    return result if isinstance(result, dict) else {"data": result}


def extract_goods_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    result = unwrap_jd_response(data)
    payload = result.get("data", result)
    candidates: list[Any] = []
    if isinstance(payload, dict):
        for key in ("goodsResp", "jfGoodsResp", "rankGoodsResp", "bigFieldGoodsResp"):
            if key in payload:
                candidates.extend(as_list(payload[key]))
        for nested_key in ("data", "list"):
            value = payload.get(nested_key)
            if isinstance(value, dict):
                for key in ("goodsResp", "jfGoodsResp", "rankGoodsResp", "bigFieldGoodsResp"):
                    if key in value:
                        candidates.extend(as_list(value[key]))
            elif isinstance(value, list):
                candidates.extend(value)
    elif isinstance(payload, list):
        candidates.extend(payload)

    return [normalize_jd_good(item) for item in candidates if isinstance(item, dict)]


def normalize_jd_good(item: dict[str, Any]) -> dict[str, Any]:
    price_info = item.get("priceInfo") or {}
    purchase_info = item.get("purchasePriceInfo") or {}
    coupon_info = item.get("couponInfo") or {}
    coupon = (
        nested(coupon_info, "couponList", "coupon")
        or nested(purchase_info, "couponList", "coupon")
        or {}
    )
    if isinstance(coupon, list):
        coupon = coupon[0] if coupon else {}

    sku_id = first_text(item.get("skuId"), item.get("mainSkuId"))
    material_url = first_text(item.get("materialUrl"), item.get("skuUrl"))
    if material_url and not material_url.startswith(("http://", "https://")):
        material_url = "https://" + material_url

    coupon_price = first_number(
        price_info.get("lowestCouponPrice"),
        price_info.get("lowestPrice"),
        purchase_info.get("purchasePrice"),
    )
    raw_price = first_number(price_info.get("price"), item.get("wlprice"), item.get("price"))
    buy_price = first_number(coupon_price, raw_price)

    return {
        "sku_id": sku_id,
        "item_id": first_text(item.get("itemId"), item.get("oriItemId"), item.get("callerItemId")),
        "name": first_text(item.get("skuName"), item.get("goodsName")),
        "material_url": material_url,
        "image_url": first_text(
            nested(item, "imageInfo", "whiteImage"),
            item.get("imageUrl"),
            item.get("imgUrl"),
        ),
        "price": raw_price,
        "coupon_price": coupon_price,
        "buy_price": buy_price,
        "coupon_link": first_text(coupon.get("link"), item.get("couponUrl")),
        "coupon_discount": first_number(coupon.get("discount")),
        "coupon_quota": first_number(coupon.get("quota")),
        "commission_share": first_number(nested(item, "commissionInfo", "commissionShare"), item.get("commissionShare")),
        "shop_name": first_text(nested(item, "shopInfo", "shopName"), item.get("shopName")),
        "owner": first_text(item.get("owner")),
        "raw": item,
    }
