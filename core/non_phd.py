# core/non_phd.py
from __future__ import annotations
from typing import Dict, List
import os
import traceback

from core.storage import load_json, save_json, now_iso
from core.utils import Utils

NON_PHD_FILENAME = "non_phd_candidates.json"

# 内部调试开关：不改变任何对外接口（需要时改为 True 便于观察写盘日志）
_DEBUG = False


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _file_path(country: str, school: str, data_dir: str = "data") -> str:
    """
    返回 data/<country>/<school>/non_phd_candidates.json
    """
    base = os.path.join(data_dir, country, school)
    _ensure_dir(base)
    return os.path.join(base, NON_PHD_FILENAME)


def _log(msg: str) -> None:
    if _DEBUG:
        print(f"[non_phd] {msg}")


def _safe_load(path: str) -> List[Dict]:
    try:
        arr = load_json(path) or []
        if not isinstance(arr, list):
            _log(f"WARN: {path} content is not a list, reset to [].")
            return []
        return arr
    except Exception as e:
        _log(f"WARN: load_json failed for {path}: {e}")
        if _DEBUG:
            traceback.print_exc()
        return []


def _safe_save(path: str, arr: List[Dict]) -> None:
    try:
        _ensure_dir(os.path.dirname(path))
        save_json(path, arr)
        _log(f"saved {len(arr)} records -> {path}")
    except Exception as e:
        # 不改变接口行为，但至少输出便于定位的问题
        print(f"[non_phd] ERROR: save_json failed for {path}: {e}")
        traceback.print_exc()


def _canonicalize(item: Dict) -> Dict:
    """
    规范化为统一 8 字段（任何缺失字段用默认值补齐）：
    id, title, position, posted_at, deadline, url, status, scraped_at
    """
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    rec_id = (item.get("id") or Utils.make_id(title, url) or "").strip()
    if not rec_id:
        # 极端保护：title/url 都空或 make_id 返回空时，确保有稳定 id
        rec_id = Utils.make_id(title or "nonphd", url or now_iso())

    rec = {
        "id":         rec_id,
        "title":      title,
        "position":   (item.get("position") or "").strip(),  # 非博士：保留原始职位类型或留空
        "posted_at":  Utils.coerce_date(item.get("posted_at") or "") or "",
        "deadline":  Utils.coerce_date(item.get("deadline") or "") or "",
        "url":        url,
        "status":     (item.get("status") or "open").strip(),
        "scraped_at": item.get("scraped_at") or now_iso(),
    }
    return rec


def append_non_phd(country: str, school: str, item: Dict, *, data_dir: str = "data") -> Dict:
    """
    追加 1 条非博士岗位到 data/<country>/<school>/non_phd_candidates.json（按 id 去重）。
    返回写入统计（added/updated/total/path）。
    - 若同 id 已存在：执行“非空覆盖”（仅用新值覆盖旧的空字段）。
    """
    path = _file_path(country, school, data_dir)
    arr  = _safe_load(path)

    by_id = {r.get("id"): r for r in arr if isinstance(r, dict)}
    rec = _canonicalize(item)
    old = by_id.get(rec["id"])

    added = updated = 0
    if old is None:
        by_id[rec["id"]] = rec
        added = 1
        _log(f"add: {rec['id']} | {rec['title']}")
    else:
        changed = False
        for k, v in rec.items():
            if k == "id":
                continue
            # 非空覆盖
            if v and not (old.get(k) or "").strip():
                old[k] = v
                changed = True
        updated = 1 if changed else 0
        _log(f"update({changed}): {rec['id']} | {rec['title']}")

    arr_out = list(by_id.values())
    _safe_save(path, arr_out)
    return {"added": added, "updated": updated, "total": len(arr_out), "path": path}


def bulk_append_non_phd(country: str, school: str, items: List[Dict], *, data_dir: str = "data") -> Dict:
    """
    批量追加非博士岗位；同样按 id 去重 + 非空覆盖。
    返回聚合统计（added/updated/total/path）。
    """
    path = _file_path(country, school, data_dir)
    arr  = _safe_load(path)

    by_id = {r.get("id"): r for r in arr if isinstance(r, dict)}
    added = updated = 0

    for it in items or []:
        rec = _canonicalize(it)
        old = by_id.get(rec["id"])
        if old is None:
            by_id[rec["id"]] = rec
            added += 1
            _log(f"add: {rec['id']} | {rec['title']}")
        else:
            changed = False
            for k, v in rec.items():
                if k == "id":
                    continue
                if v and not (old.get(k) or "").strip():
                    old[k] = v
                    changed = True
            if changed:
                updated += 1
            _log(f"update({changed}): {rec['id']} | {rec['title']}")

    arr_out = list(by_id.values())
    _safe_save(path, arr_out)
    return {"added": added, "updated": updated, "total": len(arr_out), "path": path}


# —— 追加到 core/non_phd.py 末尾 —— #

class NonPhDCollector:
    """
    用法：
      with NonPhDCollector(country="sweden", school="miun", data_dir="data") as nonphd:
          ...
          if 不是博士:
              nonphd.add({... 统一8字段或子集 ...})
          ...
      # 退出 with 时自动写入 data/<country>/<school>/non_phd_candidates.json
    """
    def __init__(self, country: str, school: str, *, data_dir: str = "data"):
        self.country = country
        self.school = school
        self.data_dir = data_dir
        self._buf = {}  # id -> record

    def add(self, item: Dict) -> None:
        rec = _canonicalize(item)
        # 防止空/重复 id 覆盖问题：在 _canonicalize 里已兜底保证非空
        self._buf[rec["id"]] = rec
        _log(f"buffer add: {rec['id']} | {rec['title']}")

    def commit(self) -> Dict:
        if not self._buf:
            # 返回和 bulk_append_non_phd 结构一致
            path = _file_path(self.country, self.school, self.data_dir)
            try:
                cur = _safe_load(path)
            except Exception:
                cur = []
            _log(f"commit: buffer empty, current file size={len(cur)} -> {path}")
            return {"added": 0, "updated": 0, "total": len(cur), "path": path}
        recs = list(self._buf.values())
        self._buf.clear()
        _log(f"commit: writing {len(recs)} records...")
        return bulk_append_non_phd(self.country, self.school, recs, data_dir=self.data_dir)

    # 上下文管理：自动提交
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            res = self.commit()
            _log(f"__exit__: {res}")
        except Exception as e:
            # 不让提交异常影响主流程，但至少输出错误细节，便于定位
            print(f"[non_phd] ERROR during commit on __exit__: {e}")
            traceback.print_exc()
        # 不吞掉原异常
        return False
