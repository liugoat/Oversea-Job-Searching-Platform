# scrapers/slovenia/uni_lj_doctoralProg.py

from __future__ import annotations

from typing import List, Dict
from urllib.parse import urljoin
import re

import requests
from bs4 import BeautifulSoup

from core.utils import Utils
from core.storage import now_iso


LIST_URL = "https://www.uni-lj.si/en/study/doctoral-study/programmes"


def fetch() -> List[Dict]:
    """
    抓取 University of Ljubljana 官方博士项目列表。

    不筛选博士/非博士——本页本身就是 doctoral programmes，
    页面里有什么就抓什么。

    返回字段遵守你系统的 Program 精简模型：
      - id
      - title
      - position
      - url
      - status
      - scraped_at
      - deadline
      - posted_at
    """
    resp = requests.get(LIST_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    scraped_at = now_iso()
    items: List[Dict] = []

    # 结构：
    # <div role="rowgroup">
    #   <div class="row" role="row">
    #     <div class="cell" role="cell">
    #       <p class="cell-title"><strong>Programme title</strong></p>
    #       <p><a href="/en/programmes/architecture">Architecture</a></p>
    #     </div>
    #     ... 其他 cell (Duration, ECTS, Provider, Feature, Study level) ...
    #   </div>
    #   ... 多个 row ...
    # </div>
    #
    # 我们只关心每个 row 里的第一个 cell 里的 a[href]。
    for row in soup.select('div[role="rowgroup"] div.row[role="row"]'):
        first_cell = row.select_one("div.cell")
        if not first_cell:
            continue

        a = first_cell.select_one("p a[href]")
        if not a:
            continue

        href = (a.get("href") or "").strip()
        if not href:
            continue

        # 规范化标题文本，避免多空格/换行
        raw_title = a.get_text(" ", strip=True)
        title = re.sub(r"\s+", " ", raw_title).strip()
        if not title:
            continue

        url = urljoin(LIST_URL, href)

        item = {
            # 用模块名前缀 + title + url 生成稳定唯一 ID
            "id": Utils.make_id("uni_lj_doctoralProg", title, url),

            # 只要项目名本身，例如 "Architecture", "Economics and business"
            "title": title,

            # Program 类型统一写成 PhD Program（与你其他 Prog 保持一致）
            "position": "PhD Program",

            "url": url,
            "status": "open",
            "scraped_at": scraped_at,

            # 列表页没有发布时间/截止时间，按约定留空字符串
            "deadline": "",
            "posted_at": "",
        }

        items.append(item)

    if not items:
        # 如果未来结构变了，一条都没抓到，抛异常方便日志排查
        raise RuntimeError("No doctoral programmes found on University of Ljubljana page.")

    return items
