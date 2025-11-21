# scrapers/france/pslProg.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import List, Dict

from core.utils import Utils
from core.storage import now_iso

LIST_URL = "https://psl.eu/en/education/find-your-curriculum/psl-phd-tracks"
HOST = "https://psl.eu"
HEADERS = {
    "User-Agent": "LLM-Scraper/1.0 (+https://example.org; contact: crawler@example.org)"
}

def _abs_url(href: str) -> str:
    if not href:
        return ""
    return href if href.startswith("http") else (HOST + href if href.startswith("/") else "https://" + href.lstrip("/"))

def fetch() -> List[Dict]:
    """
    静态抓取 PhD tracks（Program 精简模型）：
    - 解析 <a class="block_mosaique" href="..."> 内的 <div class="title">。
    - 跳过装饰用的 <div class="block_mosaique">（无 href）。
    - Program 字段：id/title/position/url/status/scraped_at；并显式补齐 posted_at/deadline=""。
    """
    session = requests.Session()
    resp = session.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items: List[Dict] = []

    # 只取真正的链接卡片（带 href 的 a.block_mosaique）
    for a in soup.select("a.block_mosaique[href]"):
        title_el = a.select_one(".title")
        title = (title_el.get_text(" ", strip=True) if title_el else "").strip()
        url = _abs_url(a.get("href", "").strip())

        if not title or not url:
            continue  # 跳过不完整

        rec = {
            "id": Utils.make_id(title, url),
            "title": title,
            "position": "PhD Program",
            "posted_at": "",     # Program 精简：显式置空
            "deadline": "",      # Program 精简：显式置空
            "url": url,
            "status": "open",    # 页面未标注关闭，默认 open
            "scraped_at": now_iso(),
        }
        items.append(rec)

    return items
