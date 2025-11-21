# scrapers/france/kedge_bizProg.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from core.utils import Utils
from core.storage import now_iso

BASE_URL = "https://student.kedge.edu"
START_URL = "https://student.kedge.edu/programmes/phd-doctor-of-philosophy-in-business-administration"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch():
    resp = requests.get(START_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    seen_ids = set()

    # 这几个研究中心链接都在 <ul><li><a> 里，href 里包含 /centres-of-excellence/
    for a in soup.select("ul li a[href*='/centres-of-excellence/']"):
        title = a.get_text(strip=True)
        href = a.get("href", "").strip()
        if not title or not href:
            continue

        # 绝对 URL（既兼容相对链接，也兼容已是 https://... 的绝对链接）
        url = urljoin(START_URL, href)

        # 稳定 id
        id_ = Utils.make_id(title, url)
        if id_ in seen_ids:
            continue
        seen_ids.add(id_)

        items.append({
            "id": id_,
            "title": title,
            "position": "PhD Program",  # Program 统一用这个类型
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),
            "deadline": "",
            "posted_at": "",
        })

    return items
