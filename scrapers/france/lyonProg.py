# scrapers/france/lyonProg.py
from typing import List, Dict, Optional
from urllib.parse import urljoin
import re
import requests
from bs4 import BeautifulSoup

from core.utils import Utils
from core.storage import now_iso

BASE = "https://www.universite-lyon.fr"
LIST_URL = "https://www.universite-lyon.fr/research/phd/18-doctoral-schools/our-18-doctoral-schools-9578.kjsp"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LLM-Scraper/1.0)"}

# 仅接受以 “ED <digits>” 开头的标题（宽容空格）
ED_TITLE = re.compile(r"^\s*ED\s*\d+\b", re.IGNORECASE)

def _fetch(url: str, timeout: int = 25) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.ok and r.text:
            return r.text
    except Exception:
        pass
    return None

def _text(el) -> str:
    if not el:
        return ""
    # 只取 a 标签的直系文本，避免把子元素的长段落拼进来
    txt = "".join(el.find_all(string=True, recursive=False)).strip()
    if not txt:
        # 退化：用 get_text 但折叠空白，并截掉换行后的冗余描述
        txt = el.get_text(" ", strip=True)
        # 若包含破折号/长横线后的说明，保留整行（项目名通常都在前半）
    return re.sub(r"\s+", " ", txt)

def fetch() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []

    html = _fetch(LIST_URL)
    if not html:
        return items

    soup = BeautifulSoup(html, "html.parser")

    # 1) 尽量收窄到列表容器（页面有内容区块，如 #content / .k-content 等）
    container = (
        soup.select_one("#content") or
        soup.select_one("#main") or
        soup.select_one(".k-content, .entry-content, .content, .contenu") or
        soup
    )

    # 2) 在容器内找链接（站点常用 lien_interne / lien_externe）
    anchors = container.select("a.lien_interne[href], a.lien_externe[href]")
    if not anchors:
        anchors = container.select("a[href]")

    out: List[Dict[str, str]] = []
    for a in anchors:
        title = _text(a)
        if not title:
            continue

        # —— 语义闸：严格要求 “ED <digits> …” 开头 ——
        if not ED_TITLE.match(title):
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

    # 去重后返回（应为 18 条）
    return list({r["id"]: r for r in out}.values())
