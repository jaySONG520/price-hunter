from __future__ import annotations

import re
from dataclasses import dataclass


PRICE_PATTERN = re.compile(
    r"(?:[¥￥]\s*([1-9]\d{2,5})(?:\.\d{1,2})?|(?:^|\s)([1-9]\d{2,5})(?:\.\d{1,2})?\s*元|^([1-9]\d{2,5})$)"
)
CONDITION_TERMS = ["全新", "未拆", "未开封", "仅拆", "拆封", "国行", "发票", "保修", "个人送保"]
BAD_TERMS = ["求购", "回收", "换", "定金", "订金", "链接", "引流"]


@dataclass(frozen=True)
class ParsedSample:
    title: str
    price: float
    condition: str


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def detect_condition(text: str) -> str:
    found = [term for term in CONDITION_TERMS if term in text]
    return " ".join(found) if found else ""


def likely_bad_listing(text: str) -> bool:
    return any(term in text for term in BAD_TERMS)


def parse_xianyu_text(text: str, include: list[str] | None = None, exclude: list[str] | None = None) -> list[dict]:
    include = [item.strip().lower() for item in include or [] if item.strip()]
    exclude = [item.strip().lower() for item in exclude or [] if item.strip()]
    lines = [normalize_space(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    samples: list[ParsedSample] = []
    previous_title = ""

    for line in lines:
      match = PRICE_PATTERN.search(line)
      if not match:
          if len(line) >= 4:
              previous_title = line
          continue

      price = float(next(group for group in match.groups() if group))
      title = normalize_space(line)
      if len(title) <= 12 and previous_title:
          title = normalize_space(f"{previous_title} {title}")
      elif previous_title and previous_title not in title and len(previous_title) <= 80:
          title = normalize_space(f"{previous_title} {title}")

      lowered = title.lower().replace(" ", "")
      if include and not all(keyword.replace(" ", "") in lowered for keyword in include):
          previous_title = ""
          continue
      if exclude and any(keyword.replace(" ", "") in lowered for keyword in exclude):
          previous_title = ""
          continue
      if likely_bad_listing(title):
          previous_title = ""
          continue

      samples.append(ParsedSample(title=title, price=price, condition=detect_condition(title)))
      previous_title = ""

    return [sample.__dict__ for sample in samples]
