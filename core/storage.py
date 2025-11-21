import os, json
from datetime import datetime, timezone

def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def now_iso():
    """绝对时间，带 UTC 时区标记"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
