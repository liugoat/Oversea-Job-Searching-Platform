# scrapers/france/uparisProg.py
from typing import List, Dict, Optional
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from core.utils import Utils
from core.storage import now_iso

BASE = "https://u-paris.fr"
LIST_URL = "https://u-paris.fr/who-am-i/en/doctoral-schools/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LLM-Scraper/1.0; +https://example.invalid)"
}

def _fetch(url: str, timeout: int = 25) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.ok and r.text:
            return r.text
    except Exception:
        pass
    return None

def _text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def fetch() -> List[Dict[str, str]]:
    """
    Paris Cité Doctoral Schools（全部为博士项目）：
    仅输出 id, title, position='doctoral program', url, status='open', scraped_at；
    其他字段留空字符串。
    """
    items: List[Dict[str, str]] = []

    html = _fetch(LIST_URL)
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")

    # 项目标题主要在正文 h3；加几个兜底选择器以防结构微调
    headers = (
        soup.select("main h3")
        or soup.select("article h3")
        or soup.select(".entry-content h3, .content h3, .wp-block-group h3")
        or soup.select("h3")
    )

    for h in headers:
        title = _text(h)
        if not title:
            continue

        # 尝试就近获取链接：标题内/附近的 <a>；否则用页面锚点或列表页
        a = h.find("a", href=True) or h.find_parent("a", href=True)
        if a and a.get("href"):
            href = a["href"].strip()
            url = href if href.startswith("http") else urljoin(BASE, href)
        else:
            hid = h.get("id")
            url = LIST_URL + f"#{hid}" if hid else LIST_URL

        items.append({
            "id": Utils.make_id(title, url),
            "title": title,
            "position": "doctoral program",
            "posted_at": "",
            "deadline": "",
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),
        })

    # 去重（按 id）
    return list({r["id"]: r for r in items}.values())
