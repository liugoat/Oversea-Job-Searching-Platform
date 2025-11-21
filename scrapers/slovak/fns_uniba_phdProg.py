# scrapers/slovak/fns_uniba_phdProg.py

from __future__ import annotations

from typing import List, Dict
from urllib.parse import urljoin
import re

import requests
from bs4 import BeautifulSoup

from core.utils import Utils
from core.storage import now_iso


LIST_URL = "https://fns.uniba.sk/en/phd-study-programmes/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _parse_programs(html: str, scraped_at: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict] = []

    # 容器 div：有时 id 可能不同，这里先尝试你给的 id，再退而求其次
    container = soup.find("div", id="c126088") or soup.find("div", class_="csc-default")
    if container is None:
        raise RuntimeError("Cannot find main container div on FNS UNIBA PhD page.")

    seen = set()
    for a in container.select("p a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue

        if "/en/study/doctoral-studies/phd-study-programmes/" not in href:
            continue

        url = urljoin(LIST_URL, href)

        raw_title = a.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", raw_title).strip()
        if not title:
            continue

        key = (title, url)
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "id": Utils.make_id("fns_uniba_phdProg", title, url),
            "title": title,
            "position": "PhD Program",
            "url": url,
            "status": "open",
            "scraped_at": scraped_at,
            "deadline": "",
            "posted_at": "",
        })

    return items


def fetch() -> List[Dict]:
    scraped_at = now_iso()
    html = None

    # 1. 优先尝试 requests（静态）
    try:
        resp = requests.get(LIST_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except requests.exceptions.SSLError as e:
        # 明确标记是 SSL 问题，后面尝试 Selenium
        html = None
        print(f"[WARN] SSL error on requests.get for FNS UNIBA: {e}")
    except requests.exceptions.RequestException as e:
        html = None
        print(f"[WARN] Network error on requests.get for FNS UNIBA: {e}")

    items: List[Dict] = []

    if html:
        items = _parse_programs(html, scraped_at)

    # 2. 如果 requests 失败或解析不到任何项目，尝试 Selenium 兜底
    if (not html or not items) and hasattr(Utils, "selenium_open"):
        driver = None
        try:
            driver = Utils.selenium_open(LIST_URL)

            # 如果你的 Utils 里有 wait/scroll，可以按需要调用
            if hasattr(Utils, "selenium_wait"):
                try:
                    Utils.selenium_wait(driver, css="h2 a")
                except Exception:
                    pass

            html = driver.page_source
            items = _parse_programs(html, scraped_at)
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    if not items:
        raise RuntimeError("No PhD study programmes found on FNS UNIBA page (requests + Selenium).")

    return items
