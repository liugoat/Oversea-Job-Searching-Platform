# scrapers/france/grenobleProg.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Set

from core.utils import Utils
from core.storage import now_iso

LIST_URL = ("https://doctorat.univ-grenoble-alpes.fr/doctoral-college/doctoral-schools/"
            "the-doctoral-schools-of-the-universite-grenoble-alpes-838517.kjsp?RH=1611137631044")
HOST = "https://doctorat.univ-grenoble-alpes.fr"
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
    静态抓取 UGA 各 Doctoral School（Program 精简模型）：
    - 标题与链接：a.liste__objets__titre.lien_interne[href]
    - 页面无关闭标识，status 默认 'open'
    - 显式补齐 posted_at / deadline 为 ""（与统一数据模型对齐）
    """
    session = requests.Session()
    resp = session.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items: List[Dict] = []
    seen: Set[str] = set()

    # 每个卡片在 <li class="liste__objets__style0045 ..."> 内，
    # 目标链接位于 <a class="liste__objets__titre lien_interne" href="..."><em>Title</em></a>
    for a in soup.select("a.liste__objets__titre.lien_interne[href]"):
        url = _abs_url(a.get("href", "").strip())
        # 标题文本位于 <em>…</em>，但直接取 a 的可见文本也可
        title_el = a.find("em") or a
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
            "status": "open",
            "scraped_at": now_iso(),
        })

    return items
