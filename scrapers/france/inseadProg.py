# scrapers/france/inseadProg.py

import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from core.utils import Utils
from core.storage import now_iso

BASE_URL = "https://www.insead.edu"
LIST_URL = "https://www.insead.edu/phd/academics-and-research"

def _fetch_html(url: str) -> str:
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False
        }
    )
    resp = scraper.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text

def _parse_program_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")

    items = []

    # 查找 “Accounting” 等关键词出现处
    # 比如查找所有 h3 或 strong 标签包含这些领域
    for heading in soup.find_all(['h3','h2','strong','p']):
        text = heading.get_text(strip=True)
        # 简单判断是否为一个 “领域名字” —— 可以根据你预期的8个名字：
        field_names = {
            "Accounting",
            "Decision Sciences",
            "Entrepreneurship",
            "Finance",
            "Marketing",
            "Organisational Behaviour",
            "Strategy",
            "Technology and Operations Management"
        }
        if text in field_names:
            title = text
            # 获取描述：可能在 heading 下一个 sibling 的 <div> 或 <p>
            desc = ""
            nxt = heading.find_next_sibling()
            if nxt:
                desc = nxt.get_text(strip=True)

            # 构造 URL：假设链接在 heading 的父 <a> 或祖先 <a>
            url = ""
            a = heading.find_parent("a")
            if a and a.get("href"):
                url = urljoin(BASE_URL, a.get("href"))
            else:
                # 没找到 <a>，就 拼 BASE_URL + slug
                slug = title.lower().replace(" ","-")
                url = urljoin(BASE_URL, f"/phd-{slug}")

            items.append({
                "id": Utils.make_id("INSEAD PhD Program", title, url),
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
        print(f"[ERROR] 抓取 INSEAD 页面失败: {e}")
        return []

    records = _parse_program_cards(html)
    print(f"[INFO] INSEAD PhD Programs 抓取完成，共 {len(records)} 条。")
    return records

if __name__ == "__main__":
    rows = fetch()
    for r in rows:
        print(r)
