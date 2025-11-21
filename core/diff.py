import os
import datetime
from urllib.parse import urlparse, parse_qsl, urlencode


from core import storage
from core.utils import Utils  # 用于日期解析与标准化


def _parse_date_any(val):
    """安全解析日期：支持 datetime 或 ISO/常见字符串"""
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, str):
        try:
            # Python 3.11+ 可解析 YYYY-MM-DD 或带时区的 ISO8601
            return datetime.datetime.fromisoformat(val)
        except Exception:
            pass
        # 尝试用项目封装解析成 YYYY-MM-DD
        d = Utils.coerce_date(val)
        if isinstance(d, datetime.datetime):
            return d
        try:
            if d:
                return datetime.datetime.strptime(d, "%Y-%m-%d")
        except Exception:
            return None
    return None


def diff_and_update(country, school, new_rows, key_field="id", data_dir="data"):
    """
    增量更新：
    - 维护 current.json / archive.json
    - 自动去重与状态标记
    - 若存在 non_phd_candidates.json，则同步清理：
        * 删除已转为博士岗位的旧误分类项
        * 删除明显无效 / 垃圾链接记录（空标题、mailto、Facebook 等）
        * ✅ 新增：当本次抓到“正确博士岗位”时，即便 old non-phd 的 id 不同，也会依据 URL/标题 归一化命中并清理
    - ✅ 新增：若无 deadline 且 posted_at 超过 5 个月，则自动剔除
    - ✅ 新增：若 deadline 已过期（相对于当前 UTC 日期），则剔除
    """
    # ---- 内部工具 ----
    def _norm_url(u: str) -> str:
        """
        用于 non_phd 清理命中的 URL 规范化：
        - 保留 netloc+path（小写，去尾斜杠）
        - 丢弃跟踪参数（utm_*, gclid 等）
        - 仅保留能区分职位的“ID 型”参数（如 id/jobId/vacancyId/query/guid，或纯数字/uuid-like）
        - 对保留的参数按 key 排序，稳定输出
        - 丢弃 fragment
        """
        if not u or not isinstance(u, str):
            return ""
        try:
            p = urlparse(u.strip())
            netloc = (p.netloc or "").lower()
            path = (p.path or "").rstrip("/")

            # 拆 query
            raw = dict(parse_qsl(p.query, keep_blank_values=True))

            # 1) 去跟踪参数
            TRACKERS = {
                "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                "gclid", "fbclid", "mc_cid", "mc_eid", "pk_campaign", "pk_kwd", "ref"
            }
            for k in list(raw.keys()):
                if k.lower() in TRACKERS:
                    raw.pop(k, None)

            # 2) 只留“ID 型”参数
            KEEP = {"id", "jobid", "job_id", "vacancyid", "vacancy_id", "positionid", "position_id", "query", "guid"}
            keep = {}
            for k, v in raw.items():
                kl = k.lower()
                if kl in KEEP:
                    keep[k] = v
                    continue
                # 形态判断：纯数字或 uuid/hex-like
                vv = (v or "").lower()
                if vv.isdigit() or (len(vv) in (16, 32, 36) and all(c in "0123456789abcdef-" for c in vv)):
                    keep[k] = v

            query = "?" + urlencode(sorted(keep.items()), doseq=True) if keep else ""
            return f"{netloc}{path}{query}"
        except Exception:
            # 兜底：去 fragment，保留原 query（宁愿不过度合并）
            u = u.split("#", 1)[0].rstrip("/")
            return u.lower()

    def _domain(u: str) -> str:
        try:
            return (urlparse(u).netloc or "").lower()
        except Exception:
            return ""

    def _norm_title(t: str) -> str:
        # 使用你项目里的规范化（小写、折叠空格、破折号统一等）
        return Utils.normalize(t or "", lower=True, collapse_spaces=True)

    # ---- 路径 ----
    school_dir = os.path.join(data_dir, country, school)
    cur_path = os.path.join(school_dir, "current.json")
    arc_path = os.path.join(school_dir, "archive.json")
    non_phd_path = os.path.join(school_dir, "non_phd_candidates.json")

    # ---- 加载旧数据 ----
    old_rows = storage.load_json(cur_path)
    old_keys = {row.get(key_field): row for row in old_rows}

    # ---- 1️⃣ 新数据预清理：剔除过期岗位（deadline 过期 / 无 deadline 且 posted_at 太久）----
    cleaned_new_rows = []
    now_dt = datetime.datetime.utcnow()
    today = now_dt.date()
    for r in new_rows:
        posted_raw = (r.get("posted_at") or "").strip()
        deadline_raw = (r.get("deadline") or "").strip()

        # A) 若给了 deadline：若 deadline < 今天（UTC），则认为已过期 → 直接丢弃
        if deadline_raw:
            deadline_dt = _parse_date_any(deadline_raw)
            try:
                if deadline_dt and deadline_dt.date() < today:
                    # deadline 已过期，剔除该记录
                    continue
            except Exception:
                # 解析异常则忽略过期判断，按下方逻辑继续
                pass
            # deadline 未过期（或无法比较）→ 保留
            cleaned_new_rows.append(r)
            continue

        # B) 未给 deadline：用 posted_at 做时效性过滤（> 150 天剔除）
        posted_date = _parse_date_any(posted_raw)
        if not posted_date:
            cleaned_new_rows.append(r)
            continue

        try:
            delta = now_dt - posted_date
            # 若超过 150 天（约 5 个月），则视为过期
            if delta.days > 150:
                continue
        except Exception:
            # 容错：无法比较则保留
            pass

        cleaned_new_rows.append(r)

    new_rows = cleaned_new_rows
    new_keys = {row.get(key_field): row for row in new_rows}

    # ---- 2️⃣ 新增与更新 ----
    added, removed = [], []
    for k, new_row in new_keys.items():
        if not k:
            continue
        if k not in old_keys:
            added.append(new_row)
        else:
            old_row = old_keys[k]
            # 非空覆盖合并
            merged = {
                **old_row,
                **{kk: vv for kk, vv in new_row.items() if vv not in ("", None)},
            }
            new_keys[k] = merged

    # ---- 3️⃣ 缺失项 → 关闭并归档 ----
    for k, old_row in old_keys.items():
        if k not in new_keys:
            old_row["status"] = "closed"
            old_row["closed_at"] = old_row.get("closed_at") or storage.now_iso()
            removed.append(old_row)

    # ---- 4️⃣ 保存 current 与 archive ----
    storage.save_json(cur_path, list(new_keys.values()))
    if removed:
        archive = storage.load_json(arc_path) + removed
        storage.save_json(arc_path, archive)

    # ---- 5️⃣ 清理 non_phd_candidates.json（强化版） ----
    if os.path.exists(non_phd_path):
        try:
            non_phd_rows = storage.load_json(non_phd_path)

            # a) 预生成“本次博士岗位”的多重匹配 Key（除 id 外，用 URL/标题的归一化来命中）
            phd_url_norm_set = set()
            phd_title_norm_by_domain = {}
            for r in new_rows:
                url = (r.get("url") or "").strip()
                title = (r.get("title") or "").strip()
                if url:
                    phd_url_norm_set.add(_norm_url(url))
                    d = _domain(url)
                    if title and d:
                        phd_title_norm_by_domain.setdefault(d, set()).add(_norm_title(title))

            cleaned_rows = []
            seen_dedup = set()  # 去重：基于 (norm_url) 或 (domain, norm_title)

            for r in non_phd_rows:
                k = r.get(key_field)
                title = (r.get("title") or "").strip()
                url_raw = (r.get("url") or "").strip()
                url_low = url_raw.lower()

                # 跳过垃圾项
                if (
                    not title
                    or len(title) < 5
                    or not url_low.startswith("http")
                    or any(x in url_low for x in [
                        "mailto:", "facebook.com", "twitter.com",
                        "linkedin.com", "instagram.com"
                    ])
                ):
                    continue

                # i) 原有：按 id 命中（已转博士）→ 删除
                if k and k in new_keys:
                    continue

                # ii) 新增：按“规范化 URL”命中（忽略协议/参数/锚点/尾斜杠）→ 删除
                url_key = _norm_url(url_raw)
                if url_key and url_key in phd_url_norm_set:
                    continue

                # iii) 新增：按“同域 + 标准化标题”命中 → 删除
                d = _domain(url_raw)
                tkey = _norm_title(title)
                if d and tkey and tkey in phd_title_norm_by_domain.get(d, set()):
                    continue

                # ---- 去重：避免 non_phd 内部重复/变体累积 ----
                dedup_key = ("U", url_key) if url_key else ("T", d, tkey)
                if dedup_key in seen_dedup:
                    continue
                seen_dedup.add(dedup_key)

                cleaned_rows.append(r)

            storage.save_json(non_phd_path, cleaned_rows)

        except Exception as e:
            print(f"[WARN] Failed to sync non_phd_candidates for {school}: {e}")

    return {
        "added": len(added),
        "removed": len(removed),
        "total": len(new_rows),
    }
