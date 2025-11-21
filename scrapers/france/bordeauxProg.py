# scrapers/france/bordeauxProg.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Set

from core.utils import Utils
from core.storage import now_iso

LIST_URL = "https://doctorat.u-bordeaux.fr/avant-le-doctorat/les-ecoles-doctorales"
HOST = "https://doctorat.u-bordeaux.fr"
HEADERS = {
    "User-Agent": "LLM-Scraper/1.0 (+https://example.org; contact: crawler@example.org)"
}

def _abs_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return HOST + href
    return HOST.rstrip("/") + "/" + href

def fetch() -> List[Dict]:
    """
    静态抓取波尔多大学各 Ecole doctorale（Program 精简模型）：
    - 每条卡片位于 <article class="block-pages-list-item"> 内，外层 <a href="..."> 包裹
    - 标题：<h1 class="block-pages-list-item-title">…</h1>
    - 显式补齐 posted_at / deadline 为 ""；status 默认 open
    """
    session = requests.Session()
    r = session.get(LIST_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    items: List[Dict] = []
    seen: Set[str] = set()

    # 选择器：article.block-pages-list-item 内部的 a[href]，标题在 h1.block-pages-list-item-title
    for art in soup.select("article.block-pages-list-item"):
        a = art.select_one("a[href]")
        title_el = art.select_one("h1.block-pages-list-item-title")
        url = _abs_url(a.get("href", "").strip()) if a else ""
        title = (title_el.get_text(" ", strip=True) if title_el else "").strip()

        if not title or not url:
            continue

        uid = Utils.make_id(title, url)
        if uid in seen:
            continue
        seen.add(uid)

        items.append({
            "id": uid,
            "title": title,
            "position": "PhD Program",
            "posted_at": "",     # Program 精简：显式置空
            "deadline": "",      # Program 精简：显式置空
            "url": url,
            "status": "open",    # 页面无关闭标识，默认 open
            "scraped_at": now_iso(),
        })

    return items
