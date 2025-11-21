# -*- coding: utf-8 -*-
"""
tool/job_llm_cron.py —— 纯批处理（无交互）

遍历 data/**/current.json → 对每条 open 且未过期的记录：
- 用 tool/page_chat1.fetch_page_text 智能抓正文（requests→Selenium 兜底）
- 用本地 LLM（4bit 量化，KV cache 关闭）抽取 8 字段：
  title, position, deadline, posted_at, university, country, processing_time(=scraped_at), requires_master_degree
- 写入 data_llm/<country>/<school>/current.json，增量/归档复用 core.diff.diff_and_update(key_field='id')
"""

from __future__ import annotations
import os
import sys
import json
import argparse
from typing import Dict, List, Tuple, Optional
import gc
from datetime import datetime, timedelta  # 顶部已有就不重复了

# 控制台刷新
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

from core import storage
from core.diff import diff_and_update
from core.utils import Utils

from tool.page_chat1 import LocalLLM, fetch_page_text, DEFAULT_MODEL_PATH

# ---------------- 路径解析 ----------------
def _resolve_dir(path_arg: str, *, expect_name: str) -> str:
    given = os.path.abspath(path_arg)
    if os.path.exists(given):
        print(f"[PATH] 使用路径：{given}")
        return given
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidate = os.path.abspath(os.path.join(project_root, path_arg))
    if os.path.exists(candidate):
        print(f"[PATH] 使用项目根相对路径：{candidate}")
        return candidate
    fallback = os.path.abspath(os.path.join(project_root, expect_name))
    if os.path.exists(fallback):
        print(f"[PATH] 使用项目根默认路径：{fallback}")
        return fallback
    print(f"[PATH] 路径不存在，仍将尝试：{candidate}")
    return candidate

# ---------------- 基础工具 ----------------
def _iter_current_json_files(data_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    base = os.path.abspath(data_dir)
    for root, _, files in os.walk(base):
        if "current.json" in files:
            ab = os.path.join(root, "current.json")
            rel = ab[len(base) + 1 : -len(os.sep + "current.json")]
            out.append((ab, rel.replace(os.sep, "/")))
    return out

def _load_list(path: str) -> List[Dict]:
    try:
        arr = storage.load_json(path) or []
        return arr if isinstance(arr, list) else []
    except Exception:
        try:
            with open(path, "r", encoding="utf-8") as f:
                arr = json.load(f) or []
                return arr if isinstance(arr, list) else []
        except Exception:
            return []

def _split_country_school(rel_key: str) -> Tuple[str, str]:
    parts = rel_key.split("/")
    return parts[0], "/".join(parts[1:]) if len(parts) > 1 else ""

def _strip_code_fence(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        return t.strip()
    return s

def _safe_parse_json(txt: str) -> Dict:
    """
    更鲁棒的 JSON 解析：
    - 先去掉代码块围栏
    - 直接 json.loads；若得到 list，取第一个 dict
    - 若失败，再从原始文本中用正则截取第一个 {...} 片段再 loads
    - 失败则返回 {}
    """
    t = _strip_code_fence(txt)
    # 第一轮直读
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            for el in obj:
                if isinstance(el, dict):
                    return el
            return {}
    except Exception:
        pass

    # 第二轮：从原文里挖出第一个 {...} 尝试
    import re as _re
    m = _re.search(r"\{[\s\S]*\}", t)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                for el in obj:
                    if isinstance(el, dict):
                        return el
        except Exception:
            pass
    return {}


def _coerce_date_yyyy_mm_dd(s: Optional[str]) -> str:
    if not s or not isinstance(s, str):
        return "NaN"
    d = Utils.coerce_date(s)
    return d if d else "NaN"

def _deadline_expired(deadline_str: Optional[str]) -> bool:
    if not deadline_str or str(deadline_str).strip().lower() == "nan":
        return False
    d = Utils.coerce_date(deadline_str)
    if not d:
        return False
    try:
        ddl = datetime.strptime(d, "%Y-%m-%d").date()
        return ddl < datetime.utcnow().date()
    except Exception:
        return False

def _posted_too_old(posted_at_str: Optional[str], *, days: int = 150) -> bool:
    """
    posted_at 存在且早于当前 UTC 日期 days 天以上 -> True（剔除）
    空/无法解析 -> 不剔除（返回 False）
    """
    if not posted_at_str or str(posted_at_str).strip().lower() == "nan":
        return False
    d = Utils.coerce_date(posted_at_str)
    if not d:
        return False
    try:
        dt = datetime.strptime(d, "%Y-%m-%d").date()
        return (datetime.utcnow().date() - dt) > timedelta(days=days)
    except Exception:
        return False


# ---------------- 提示词 ----------------
def _extraction_prompt() -> str:
    return (
        "你是一名信息抽取助手。必须严格基于 <DOC> 原文回答；除非字段明确允许推理，否则禁止猜测。"
        "凡文档未出现或无法确定的字段，一律返回字符串 \"NaN\"（必须是字符串）。\n"
        "请仅输出一个 JSON 对象（不要任何多余文字或代码块标记），键名与要求如下：\n"
        "{\n"
        "  \"title\": (string | \"NaN\"),\n"
        "  \"position\": (\"Doctoral student\" | \"PhD Program\" | \"NaN\"),\n"
        "  \"deadline\": (\"YYYY-MM-DD\" | \"NaN\"),\n"
        "  \"posted_at\": (\"YYYY-MM-DD\" | \"NaN\"),\n"
        "  \"university\": (string | \"NaN\"),\n"
        "  \"country\": (string | \"NaN\"),\n"
        "  \"processing_time\": (\"NaN\"),\n"
        "  \"requires_master_degree\": (string | \"NaN\")\n"
        "}\n"
        "补充与限制：\n"
        "1) university/country 可在证据充分时补全；无法确定则 \"NaN\"；\n"
        "2) deadline/posted_at 必须是 YYYY-MM-DD；非标准（如 “21 févr.”、“Oct 2025”、“rolling”）→ \"NaN\"；\n"
        "3) processing_time 固定填 \"NaN\"（外部用 scraped_at 覆盖）；\n"
        "4) requires_master_degree：仅总结“明确出现的学位层级与专业/学科要求”，需中英双语；未提及或模糊 → \"NaN\"；\n"
        "5) 只输出该 JSON，不要其它文字。"
    )

# ---------------- LLM 调用 ----------------
def _summarize_record(llm: LocalLLM, url: str, *, user_question: Optional[str]) -> Dict:
    doc = fetch_page_text(url)
    # ✅ 再加一道字符级截断，防极端长文
    if len(doc) > 60_000:
        doc = doc[:60_000]

    sys_prompt = _extraction_prompt()
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "system", "content": f"<DOC>\n{doc}\n</DOC>"},
    ]
    if user_question:
        messages.append({"role": "user", "content": user_question})

    # --- 生成 ---
    raw = llm.chat(messages, max_new_tokens=180, temperature=0.2, top_p=0.9)

    # --- 更鲁棒的 JSON 解析 ---
    def _robust_parse(txt: str) -> Dict:
        t = _strip_code_fence(txt)

        # 1) 直读
        try:
            obj = json.loads(t)
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                for el in obj:
                    if isinstance(el, dict):
                        return el
                return {}
        except Exception:
            pass

        # 2) 正则抽取首个 {...}
        import re as _re
        m = _re.search(r"\{[\s\S]*\}", t)
        if m:
            try:
                obj = json.loads(m.group(0))
                if isinstance(obj, dict):
                    return obj
                if isinstance(obj, list):
                    for el in obj:
                        if isinstance(el, dict):
                            return el
            except Exception:
                pass
        return {}

    parsed = _robust_parse(raw)
    if not isinstance(parsed, dict):
        print("[WARN] LLM JSON 不是对象，已忽略，原始输出片段：",
              (raw[:200] + "...") if isinstance(raw, str) and len(raw) > 200 else raw)

        parsed = {}

    # --- 字段安全取值与规范化 ---
    title     = parsed.get("title") if isinstance(parsed.get("title"), str) else "NaN"
    position  = parsed.get("position") if isinstance(parsed.get("position"), str) else "NaN"
    deadline  = _coerce_date_yyyy_mm_dd(parsed.get("deadline"))
    posted_at = _coerce_date_yyyy_mm_dd(parsed.get("posted_at"))
    university = parsed.get("university") if isinstance(parsed.get("university"), str) else "NaN"
    country    = parsed.get("country") if isinstance(parsed.get("country"), str) else "NaN"
    requires_master_degree = parsed.get("requires_master_degree")
    requires_master_degree = requires_master_degree if isinstance(requires_master_degree, str) else "NaN"

    return {
        "title": title if title is not None else "NaN",
        "position": position if position is not None else "NaN",
        "deadline": deadline,
        "posted_at": posted_at,
        "university": university if university is not None else "NaN",
        "country": country if country is not None else "NaN",
        "processing_time": "NaN",  # 稍后用 scraped_at 覆盖
        "requires_master_degree": requires_master_degree,
    }


# ---------------- 批处理主体 ----------------
def run_batch(
    data_dir: str,
    out_dir: str,
    model_path: str,
    user_question: Optional[str],
    include_closed: bool,
    include_expired: bool,
    limit_per_school: Optional[int],
) -> Dict:
    res = {"schools": 0, "items": 0, "errors": []}
    files = _iter_current_json_files(data_dir)
    if not files:
        print(f"[BATCH] 未在 {data_dir} 下找到任何 current.json。")
        return res

    print(f"[BATCH] 发现 {len(files)} 个 school 的 current.json。", flush=True)

    # ✅ 4bit量化实例（显存最省）
    llm = LocalLLM(model_path, load_in_4bit=True, max_input_tokens=3000, max_new_tokens_default=192)
    cpu_llm = None  # 懒加载CPU备份

    # 需要清缓存时用
    try:
        import torch
        _HAS_TORCH = True
    except Exception:
        _HAS_TORCH = False

    for abs_path, rel_key in files:
        country, school_path = _split_country_school(rel_key)
        try:
            items = _load_list(abs_path)
            if not items:
                continue

            new_rows: List[Dict] = []
            cnt = 0
            for it in items:
                if not include_closed and (it.get("status") or "open").lower() != "open":
                    continue
                if not include_expired and _deadline_expired(it.get("deadline")):
                    print(f"[SKIP] 过期（deadline={it.get('deadline')}）: {rel_key} | {it.get('id','?')} | {it.get('title','')}")
                    continue
                # 新增：posted_at 超过 150 天也跳过
                if not include_expired and _posted_too_old(it.get("posted_at"), days=150):
                    print(
                        f"[SKIP] posted_at 已超过 150 天（posted_at={it.get('posted_at')}）: {rel_key} | {it.get('id', '?')} | {it.get('title', '')}")
                    continue

                url = (it.get("url") or "").strip()
                if not url:
                    continue

                try:
                    extracted = _summarize_record(llm, url, user_question=user_question)
                except RuntimeError as e:
                    # ✅ OOM 自动 CPU 兜底重试一次
                    if "CUDA out of memory" in str(e) or "CUDA error" in str(e):
                        print("[WARN] 发生 OOM，切 CPU 重试一次。")
                        if cpu_llm is None:
                            cpu_llm = LocalLLM(model_path, dtype="float32",
                                               load_in_4bit=False, max_input_tokens=2800,
                                               max_new_tokens_default=160)
                        extracted = _summarize_record(cpu_llm, url, user_question=user_question)
                    else:
                        msg = f"[WARN] LLM 处理失败 {rel_key} | {it.get('id','?')} | {e}"
                        print(msg, flush=True); res["errors"].append(msg); continue
                except Exception as e:
                    msg = f"[WARN] LLM 处理失败 {rel_key} | {it.get('id','?')} | {e}"
                    print(msg, flush=True); res["errors"].append(msg); continue

                row = {
                    "id": it.get("id") or Utils.make_id(it.get("title",""), it.get("url","")),
                    "title": extracted["title"] if extracted["title"] != "NaN" else it.get("title",""),
                    "position": extracted["position"] if extracted["position"] != "NaN" else (it.get("position","") or "NaN"),
                    "deadline": extracted["deadline"],
                    "posted_at": extracted["posted_at"],
                    "university": extracted["university"],
                    "country": extracted["country"],
                    "processing_time": it.get("scraped_at") or storage.now_iso(),  # 用 scraped_at
                    "requires_master_degree": extracted["requires_master_degree"],
                    "url": url,
                    "status": it.get("status", "open"),
                    "scraped_at": it.get("scraped_at") or storage.now_iso(),
                }
                new_rows.append(row)
                cnt += 1
                res["items"] += 1

                if limit_per_school and cnt >= limit_per_school:
                    break

                # ✅ 每条后清缓存，降低碎片化风险
                if _HAS_TORCH and getattr(sys.modules.get('torch'), "cuda", None) and torch.cuda.is_available():
                    try:
                        torch.cuda.empty_cache()
                        torch.cuda.ipc_collect()
                    except Exception:
                        pass
                gc.collect()

            if new_rows:
                diff_and_update(
                    country=country,
                    school=school_path,
                    new_rows=new_rows,
                    key_field="id",
                    data_dir=out_dir,
                )
                res["schools"] += 1
                print(f"[BATCH] 写入完成：{rel_key} -> {len(new_rows)} 条。", flush=True)

        except Exception as e:
            msg = f"[ERROR] 批处理失败 {rel_key}: {e}"
            print(msg, flush=True)
            res["errors"].append(msg)

    print(f"[BATCH] 全部完成：schools={res['schools']}, items={res['items']}, errors={len(res['errors'])}", flush=True)
    return res

# ---------------- CLI ----------------
def main():
    p = argparse.ArgumentParser(description="批处理 data/**/current.json → data_llm/**（零交互、显存友好）")
    p.add_argument("--data-dir", default="data", help="源数据根目录（默认 data）")
    p.add_argument("--out-dir", default="data_llm", help="输出根目录（默认 data_llm）")
    p.add_argument("--model-path", default=DEFAULT_MODEL_PATH, help="本地模型路径")
    p.add_argument("--question", default=None, help="可选：附加用户问句（一般不需要）")
    p.add_argument("--include-closed", action="store_true", help="包含已关闭的岗位/项目")
    p.add_argument("--include-expired", action="store_true", help="包含已过期（deadline 已过去）的岗位/项目")
    p.add_argument("--limit-per-school", type=int, default=None, help="每个学校最多处理多少条（调试用）")
    args = p.parse_args()

    resolved_data = _resolve_dir(args.data_dir, expect_name="data")
    resolved_out  = _resolve_dir(args.out_dir,  expect_name="data_llm")

    run_batch(
        data_dir=resolved_data,
        out_dir=resolved_out,
        model_path=args.model_path,
        user_question=args.question,
        include_closed=args.include_closed,
        include_expired=args.include_expired,
        limit_per_school=args.limit_per_school,
    )

if __name__ == "__main__":
    main()
