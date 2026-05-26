from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


DEFAULT_CONFIG: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8765},
    "costs": {
        "xianyu_fee_rate": 0.006,
        "default_shipping": 18,
        "default_packaging": 6,
        "default_bargain_rate": 0.02,
        "min_profit_rate": 0.06,
        "min_profit_amount": 200,
    },
    "platforms": {
        "jd": {
            "enabled": False,
            "server_url": "https://router.jd.com/api",
            "app_key": "",
            "app_secret": "",
            "access_token": "",
            "site_id": "",
            "pid": "",
            "position_id": "",
            "union_id": "",
            "auth_key": "",
        }
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    for name in ("config.json", "config.local.json"):
        path = ROOT / name
        if path.exists():
            config = deep_merge(config, json.loads(path.read_text(encoding="utf-8")))

    jd = config.setdefault("platforms", {}).setdefault("jd", {})
    env_map = {
        "JD_APP_KEY": "app_key",
        "JD_APP_SECRET": "app_secret",
        "JD_ACCESS_TOKEN": "access_token",
        "JD_SITE_ID": "site_id",
        "JD_PID": "pid",
        "JD_POSITION_ID": "position_id",
        "JD_UNION_ID": "union_id",
        "JD_AUTH_KEY": "auth_key",
        "JD_SERVER_URL": "server_url",
    }
    for env_name, key in env_map.items():
        value = os.getenv(env_name)
        if value:
            jd[key] = value

    enabled_env = os.getenv("JD_ENABLED")
    if enabled_env:
        jd["enabled"] = enabled_env.lower() in {"1", "true", "yes", "on"}

    return config


def public_config_status(config: dict[str, Any]) -> dict[str, Any]:
    jd = config.get("platforms", {}).get("jd", {})
    return {
        "jd": {
            "enabled": bool(jd.get("enabled")),
            "configured": bool(jd.get("app_key") and jd.get("app_secret")),
            "has_access_token": bool(jd.get("access_token")),
            "has_site_id": bool(jd.get("site_id")),
            "has_pid": bool(jd.get("pid")),
            "server_url": jd.get("server_url") or DEFAULT_CONFIG["platforms"]["jd"]["server_url"],
        }
    }
