from __future__ import annotations

from urllib.parse import quote_plus


PLATFORMS = {
    "jd": {
        "name": "京东",
        "search_url": "https://search.jd.com/Search?keyword={query}",
        "api_status": "reserved",
    },
    "taobao": {
        "name": "淘宝",
        "search_url": "https://s.taobao.com/search?q={query}",
        "api_status": "reserved",
    },
    "tmall": {
        "name": "天猫",
        "search_url": "https://list.tmall.com/search_product.htm?q={query}",
        "api_status": "reserved",
    },
    "douyin": {
        "name": "抖音",
        "search_url": "https://www.douyin.com/search/{query}",
        "api_status": "reserved",
    },
    "xianyu": {
        "name": "闲鱼",
        "search_url": "https://www.goofish.com/search?q={query}",
        "api_status": "manual_or_authorized",
    },
}


def search_links(query: str) -> list[dict]:
    encoded = quote_plus(query)
    return [
        {
            "key": key,
            "name": value["name"],
            "url": value["search_url"].format(query=encoded),
            "api_status": value["api_status"],
        }
        for key, value in PLATFORMS.items()
    ]
