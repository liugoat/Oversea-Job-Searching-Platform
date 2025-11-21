# scrapers/france/escpProg.py
"""
ESCP Business School — Doctoral Programmes Scraper
URL: https://escp.eu/programmes/doctoral-programmes
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from core.utils import Utils
from core.storage import now_iso


LIST_URL = "https://escp.eu/programmes/doctoral-programmes"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def _parse_programs(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    # 每个博士项目
    blocks = soup.select("div.item_course a.item")
    if not blocks:
        print("[ERROR] 未找到项目块，请检查 HTML 是否更改。")
        return []

    items = []

    for a in blocks:
        # 链接
        href = a.get("href", "").strip()
        if not href:
            continue

        url = urljoin(LIST_URL, href)

        # 标题
        title_tag = a.select_one("h2.title-item")
        title = title_tag.get_text(strip=True) if title_tag else ""

        if not title:
            continue

        rec = {
            "id": Utils.make_id("ESCP Doctoral Programme", title, url),
            "title": title,
            "position": "PhD Program",
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),
            "deadline": "",
            "posted_at": "",
        }

        items.append(rec)

    return items


def fetch() -> list[dict]:
    try:
        html = _fetch_html(LIST_URL)
    except Exception as e:
        print(f"[ERROR] 抓取 ESCP 页面失败: {e}")
        return []

    records = _parse_programs(html)
    print(f"[INFO] ESCP Doctoral Programmes 抓取完成，共 {len(records)} 条。")
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
