# scrapers/france/ipparisProg.py
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Set

from core.utils import Utils
from core.storage import now_iso

LIST_URL = "https://www.ip-paris.fr/en/education/phd-track"
HOST = "https://www.ip-paris.fr"
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
    静态抓取 IP Paris PhD Track 列表（Program 精简模型）：
    - 标题：.enfant h3 a
    - 详情链接：同上（href 为相对路径）
    - 显式补齐 posted_at / deadline 为空字符串
    - status 默认 open（页面未提供关闭标识）
    """
    session = requests.Session()
    resp = session.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items: List[Dict] = []
    seen: Set[str] = set()

    # 每个项目容器：div.conteneur-enfant，内容在内层 div.enfant h3 a
    for a in soup.select(".liste-enfants .conteneur-enfant .enfant h3 a[href]"):
        title = a.get_text(" ", strip=True)
        url = _abs_url(a.get("href", "").strip())
        if not title or not url:
            continue

        # 去重（页面中同一项目通常还有“Read more”处的相同链接）
        uid = Utils.make_id(title, url)
        if uid in seen:
            continue
        seen.add(uid)

        rec = {
            "id": uid,
            "title": title,
            "position": "PhD Program",
            "posted_at": "",     # Program 精简：显式置空
            "deadline": "",      # Program 精简：显式置空
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),
        }
        items.append(rec)

    return items
