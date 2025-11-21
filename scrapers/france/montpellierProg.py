# scrapers/france/montpellierProg.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import List, Dict

from core.utils import Utils
from core.storage import now_iso

LIST_URL = "https://www.umontpellier.fr/en/recherche/etudes-doctorales-et-hdr"
HOST = "https://www.umontpellier.fr"
HEADERS = {
    "User-Agent": "LLM-Scraper/1.0 (+https://example.org; contact: crawler@example.org)"
}

def _abs_url(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return HOST + href
    return href  # 其他情况直接返回

def fetch() -> List[Dict]:
    """
    静态解析 <details class="wp-block-details">：
      - 标题: <summary> 文本
      - 链接: 块内文本为 'Website' 的 <a href="...">（若无则跳过）
      - 返回 Program 精简模型六字段 + 显式 posted_at/deadline=""
    """
    session = requests.Session()
    resp = session.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items: List[Dict] = []

    for d in soup.select("details.wp-block-details"):
        # 标题（去多余空白）
        summary = d.find("summary")
        title = (summary.get_text(" ", strip=True) if summary else "").strip()
        if not title:
            continue

        # 站点 URL：优先寻找显示文本为 "Website" 的链接
        website_a = None
        for a in d.select("a[href]"):
            txt = (a.get_text(" ", strip=True) or "").strip().lower()
            if txt == "website":
                website_a = a
                break

        if not website_a:
            # 兜底：如果没有明确的“Website”，可选第一条外链（但为了准确，这里直接跳过）
            continue

        url = _abs_url(website_a.get("href", ""))
        if not url:
            continue

        rec = {
            "id": Utils.make_id(title, url),
            "title": title,
            "position": "PhD Program",
            "posted_at": "",     # Program：显式置空
            "deadline": "",      # Program：显式置空
            "url": url,
            "status": "open",    # 页面未给关闭状态，默认 open
            "scraped_at": now_iso(),
        }
        items.append(rec)

    return items
