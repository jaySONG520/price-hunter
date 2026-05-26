from __future__ import annotations

from urllib.parse import quote_plus


PLATFORMS = {
    "jd": {
        "name": "京东",
        "search_url": "https://search.jd.com/Search?keyword={query}",
        "api_status": "optional_api",
    },
    "taobao": {
        "name": "淘宝",
        "search_url": "https://s.taobao.com/search?q={query}",
        "api_status": "optional_api",
    },
    "tmall": {
        "name": "天猫",
        "search_url": "https://list.tmall.com/search_product.htm?q={query}",
        "api_status": "optional_api",
    },
    "douyin": {
        "name": "抖音",
        "search_url": "https://www.douyin.com/search/{query}",
        "api_status": "manual",
    },
    "xianyu": {
        "name": "闲鱼",
        "search_url": "https://www.goofish.com/search?q={query}",
        "api_status": "manual_or_authorized",
    },
}


HISTORY_TOOLS = {
    "manmanbuy": {
        "name": "慢慢买历史价",
        "url": "https://tool.manmanbuy.com/history.aspx?url={query}",
    },
    "gwdang": {
        "name": "购物党",
        "url": "https://www.gwdang.com/",
    },
    "hisprice": {
        "name": "历史价格查询",
        "url": "https://www.hisprice.cn/",
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


def history_links(query_or_url: str) -> list[dict]:
    encoded = quote_plus(query_or_url)
    return [
        {
            "key": key,
            "name": value["name"],
            "url": value["url"].format(query=encoded),
        }
        for key, value in HISTORY_TOOLS.items()
    ]
