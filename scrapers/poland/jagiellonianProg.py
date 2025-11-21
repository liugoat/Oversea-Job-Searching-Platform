# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
from core.utils import Utils
from core.storage import now_iso

def fetch():
    """
    爬取雅盖隆大学（Jagiellonian University）的项目列表页面：
    https://phd.uj.edu.pl/programmes

    返回 Program 六字段模型 + 其余字段置空。
    """
    base_url = "https://phd.uj.edu.pl/programmes"
    resp = requests.get(base_url, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for div in soup.select("div.post-folded__nav"):
        title_tag = div.select_one("h3 button")
        link_tag = div.select_one("a.post-folded__link")

        title = title_tag.get_text(strip=True) if title_tag else ""
        url = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
        if url and url.startswith("/"):
            url = "https://phd.uj.edu.pl" + url

        item = {
            # --- 六字段 ---
            "id": Utils.make_id(title, url),
            "title": title,
            "position": "PhD Program",
            "url": url,
            "status": "open",
            "scraped_at": now_iso(),

            # --- 其余字段统一为空 ---
            "posted_at": "",
            "deadline": "",
        }

        items.append(item)

    return items
