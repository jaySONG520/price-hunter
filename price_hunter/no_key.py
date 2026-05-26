from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PRICE_PATTERN = re.compile(
    r"(?:[¥￥]\s*([1-9]\d{1,5})(?:\.\d{1,2})?|(?:^|\s)([1-9]\d{1,5})(?:\.\d{1,2})?\s*元|^([1-9]\d{1,5})(?:\.\d{1,2})?$)"
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
JUNK_TERMS = ["广告", "直播", "进店", "看相似", "找同款", "评价", "已售", "付款人数", "收藏"]
BAD_TERMS = ["定金", "订金", "维修", "配件", "外壳", "求购", "回收", "换购", "链接专拍"]


@dataclass(frozen=True)
class ParsedOffer:
    title: str
    price: float
    platform: str
    source_url: str = ""
    raw: str = ""
    confidence: float = 0.65


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_price(text: str) -> float | None:
    match = PRICE_PATTERN.search(text)
    if not match:
        return None
    value = next(group for group in match.groups() if group)
    try:
        return float(value)
    except ValueError:
        return None


def clean_title(text: str) -> str:
    text = URL_PATTERN.sub("", text)
    text = PRICE_PATTERN.sub("", text)
    for term in JUNK_TERMS:
        text = text.replace(term, " ")
    return normalize_space(text)


def should_keep(title: str, include: list[str] | None = None, exclude: list[str] | None = None) -> bool:
    lowered = title.lower().replace(" ", "")
    include = [item.strip().lower().replace(" ", "") for item in include or [] if item.strip()]
    exclude = [item.strip().lower().replace(" ", "") for item in exclude or [] if item.strip()]
    if include and not all(item in lowered for item in include):
        return False
    if any(item in lowered for item in exclude):
        return False
    if any(term in title for term in BAD_TERMS):
        return False
    return len(title) >= 4


def parse_offer_text(
    text: str,
    platform: str = "manual",
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[dict[str, Any]]:
    lines = [normalize_space(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    offers: list[ParsedOffer] = []
    previous_title = ""
    previous_url = ""

    for line in lines:
        url_match = URL_PATTERN.search(line)
        if url_match:
            previous_url = url_match.group(0)

        price = detect_price(line)
        if price is None:
            title = clean_title(line)
            if should_keep(title, include=None, exclude=exclude):
                previous_title = title
            continue

        title = clean_title(line)
        if previous_title and (len(title) < 8 or previous_title not in title):
            title = normalize_space(f"{previous_title} {title}")

        source_url = previous_url
        if should_keep(title, include=include, exclude=exclude):
            confidence = 0.85 if any(keyword.lower().replace(" ", "") in title.lower().replace(" ", "") for keyword in include or []) else 0.65
            offers.append(
                ParsedOffer(
                    title=title,
                    price=price,
                    platform=platform,
                    source_url=source_url,
                    raw=line,
                    confidence=confidence,
                )
            )

        previous_title = ""
        previous_url = ""

    return [offer.__dict__ for offer in offers]
