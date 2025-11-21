# scrapers/france/hecProg.py
"""
HEC Paris — Doctoral Program Research Areas 爬虫
URL: https://www.hec.edu/en/doctoral-program
静态页面，无需 Selenium。
"""

import requests
from bs4 import BeautifulSoup
from core.utils import Utils
from core.storage import now_iso


LIST_URL = "https://www.hec.edu/en/doctoral-program"

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

    # 精确匹配包含 8 个方向链接的 col-6
    right_col = None
    for div in soup.select("div.col-6"):
        if div.select_one("a.top-task-link"):
            right_col = div
            break

    if not right_col:
        print("[ERROR] 未找到 Research Areas 链接区域")
        return []

    items = []

    for a in right_col.select("a.top-task-link"):
        title = a.get_text(strip=True)
        href = a.get("href", "").strip()

        if not title or not href:
            continue

        # HEC 链接都是绝对路径，无需 urljoin
        url = href

        items.append({
            "id": Utils.make_id("HEC PhD Program", title, url),
            "title": title,
            "position": "PhD Program",
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),
            "deadline": "",
            "posted_at": "",
        })

    return items


def fetch() -> list[dict]:
    try:
        html = _fetch_html(LIST_URL)
    except Exception as e:
        print(f"[ERROR] 抓取 HEC 页面失败: {e}")
        return []

    records = _parse_programs(html)
    print(f"[INFO] HEC Paris Research Areas 抓取完成，共 {len(records)} 条（应为 8 条）。")
    return records


if __name__ == "__main__":
    for r in fetch():
        print(r)
