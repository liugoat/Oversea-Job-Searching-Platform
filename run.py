import importlib, os, json, traceback
from datetime import date
from core import diff, storage

#新增
from typing import List  # 关键：用 List 而不是 list
import importlib
import traceback
import time
from datetime import datetime


DATA_DIR = "data"
RESULTS_DIR = "results"

# 单独的数据根目录（不影响原 DATA_DIR）
DATA_WEB_DIR = "data_web"

def run_country(country: str):
    """自动加载某个国家目录下的所有爬虫并执行"""
    scrapers_pkg = f"scrapers.{country}"
    pkg = importlib.import_module(scrapers_pkg)
    report = {"country": country, "schools": [], "errors": []}

    # 找该国家的所有爬虫（__all__ 或 __init__.py 中定义）
    spiders = getattr(pkg, "__all__", [])
    print(f"[INFO] Running scrapers for {country}: {spiders}")

    for spider_name in spiders:
        try:
            spider_mod = importlib.import_module(f"{scrapers_pkg}.{spider_name}")
            fetch_func = getattr(spider_mod, "fetch", None)
            if not fetch_func:
                continue

            rows = fetch_func()
            stats = diff.diff_and_update(
                country=country,
                school=spider_name,
                new_rows=rows,
                key_field="title",   # 以 title 去重
                data_dir=DATA_DIR
            )
            report["schools"].append({
                "school": spider_name,
                **stats
            })
            print(f"[OK] {spider_name}: {stats}")

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            report["errors"].append({
                "school": spider_name,
                "error": err_msg
            })
            print(f"[ERROR] {spider_name} failed -> {err_msg}")
            traceback.print_exc()

    # 保存报告
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"report_{date.today()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"✅ {country} finished. Report saved at {path}")


def run_country_Prog(country: str):
    """
    专门运行“项目（program）”类爬虫：
    - 从 scrapers.<country>.__all_prog__ 读取清单
    - school 目录名统一加后缀 'Prog'，与岗位分开
    - 报告单独写入 results/report_YYYY-MM-DD_Prog.json
    """
    scrapers_pkg = f"scrapers.{country}"
    pkg = importlib.import_module(scrapers_pkg)
    report = {"country": country, "programs": [], "errors": []}

    spiders = getattr(pkg, "__all_prog__", [])
    print(f"[INFO] Running PROGRAM scrapers for {country}: {spiders}")

    for spider_name in spiders:
        try:
            spider_mod = importlib.import_module(f"{scrapers_pkg}.{spider_name}")
            fetch_func = getattr(spider_mod, "fetch", None)
            if not fetch_func:
                continue

            rows = fetch_func()

            # 目录名/文件名后缀加 'Prog'，与岗位分开存储  原爬取文件就有Prog后缀备注，不需要再写了
            school_key = f"{spider_name}"

            stats = diff.diff_and_update(
                country=country,
                school=school_key,   # 这里决定 data/<country>/<school_key> 路径，从而文件名含 Prog
                new_rows=rows,
                key_field="title",
                data_dir=DATA_DIR
            )
            report["programs"].append({
                "school": school_key,
                **stats
            })
            print(f"[OK][PROG] {school_key}: {stats}")

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            report["errors"].append({
                "school": spider_name,
                "error": err_msg
            })
            print(f"[ERROR][PROG] {spider_name} failed -> {err_msg}")
            traceback.print_exc()

    # 保存“项目”报告，文件名也加 _Prog
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"report_{date.today()}_Prog.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"✅ {country} PROGRAMS finished. Report saved at {path}")


def _list_countries(scrapers_root: str = "scrapers") -> List[str]:
    """列出已有的国家（scrapers/ 下含 __init__.py 的子目录）"""
    countries: List[str] = []
    for name in os.listdir(scrapers_root):
        path = os.path.join(scrapers_root, name)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
            countries.append(name)
    countries.sort()
    return countries

def _country_report_path(base_results_dir: str, country: str, today_str: str, layout: str = "flat") -> str:
    """
    生成按国报告文件路径，并确保目录存在。
    layout:
      - "flat"  -> results/<country>/<YYYY-MM-DD>.json
      - "dated" -> results/<country>/<YYYY-MM-DD>/report.json
    """
    if layout == "dated":
        dirpath = os.path.join(base_results_dir, country, today_str)
        fname = "report.json"
    else:
        dirpath = os.path.join(base_results_dir, country)
        fname = f"{today_str}.json"
    os.makedirs(dirpath, exist_ok=True)
    return os.path.join(dirpath, fname)


def main():
    # 举例：运行 sweden 全部爬虫   run_country("sweden")
    # 运行爬取项目 run_country_Prog("sweden")
    #run_all_countries_full_with_timer()
    run_country_Prog("slovak")


if __name__ == "__main__":
    main()
