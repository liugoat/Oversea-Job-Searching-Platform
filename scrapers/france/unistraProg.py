# scrapers/france/unistraProg.py
from typing import List, Dict, Optional
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from core.utils import Utils
from core.storage import now_iso

BASE = "https://en.unistra.fr"
LIST_URL = "https://en.unistra.fr/research/doctoral-schools"

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
    Strasbourg / Unistra Doctoral Schools
    输出：id, title, position='doctoral program', url, status='open', scraped_at
    其他字段置空。
    """
    items: List[Dict[str, str]] = []

    html = _fetch(LIST_URL)
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")

    # 收窄到正文容器，避免抓到页脚/导航链接
    container = (
        soup.select_one("main") or
        soup.select_one("#content") or
        soup.select_one(".content, .entry-content") or
        soup
    )

    # 该页的项目链接都在 /research/doctoral-schools/ 路径下
    anchors = container.select('a[href^="/research/doctoral-schools/"], a[href*="/research/doctoral-schools/"]')

    out: List[Dict[str, str]] = []
    for a in anchors:
        title = _text(a)
        if not title:
            continue

        href = (a.get("href") or "").strip()
        url = href if href.startswith("http") else urljoin(BASE, href)

        out.append({
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
    return list({r["id"]: r for r in out}.values())
