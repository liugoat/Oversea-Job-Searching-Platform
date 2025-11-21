# Oversea-Job-Searching-Platform


本项目用于**每日自动**爬取全球School官网与第三方岗位聚合网站发布的**岗位与项目**，并以**统一数据模型**进行本地存储与**增量更新**。  

系统强调：**一次入口**、**按国家批量**、**每校独立爬虫**、**通用去重与归档**、**错误不阻断整体运行**、**静态/动态页面自适配**、**本地 LLM 批处理抽取**。



---
## 目录结构

```
.
|-- core/ # 核心通用模块
| |-- utils.py # 工具函数（日期处理、ID 生成、规范化、博士岗判定、Selenium 基础封装：驱动创建、打开页面、等待、点击、滚动）
| |-- storage.py # JSON 读写、UTC 时间戳（now_iso）
| |-- diff.py # 增量更新（查重/合并/归档写入统计）
| -- non_phd.py # 非博士岗位收集与存储（追加、批量、收集器） | |-- scrapers/ # 各国/学校爬虫（每个学校一个文件，暴露 fetch()） | -- sweden/
| |-- init.py # 列出该国家的学校清单
| |-- lund.py
| |-- gothenburg.py
| |-- karolinska.py
| -- uppsala.py | |-- data/ # 爬取结果（每校一个目录） | -- sweden/
| |-- lund/
| | |-- current.json
| | |-- archive.json
| | -- non_phd_candidates.json |-- data_web/ # 第三方岗位聚合网站抓取结果（每站一个目录） | -- academic_transfer_web/ | |-- current.json | -- archive.json | -- academic_positions_web/ | |-- current.json | -- archive.json | |-- data_llm/ # LLM 抽取后的结构化结果（镜像 data/** 的层级） | -- sweden/ | |-- lund/ | | |-- current.json | | -- archive.json | -- ...
| |-- results/ # 每次运行的汇总报告（JSON） | |-- report_YYYY-MM-DD.json | |-- report_YYYY-MM-DD_Prog.json | |-- report_all_YYYY-MM-DD.json | |-- report_all_YYYY-MM-DD_Prog.json | |-- report_all_YYYY-MM-DD_Full.json | -- runtime_log.jsonl | |-- tool/ | |-- page_chat1.py # 智能抓正文（requests→Selenium 兜底）& 本地 LLM 对话封装 | -- job_llm_cron.py # （或 job_llm_batch.py）批处理字段抽取 → 写入 data_llm/**
| |-- scraper_jobweb/ # 聚合网站爬虫 | -- job_web/ | |-- academic_transfer_web.py | -- academic_positions_web.py
| |-- run.py # 入口脚本：按国家自动发现并运行所有学校爬虫；支持项目、聚合网站与全量运行
`-- README.md

````





---


## 数据模型（统一字段）


### 职位（Position）

每个职位是一条 JSON 记录：


每个职位是一条 JSON 记录：

- `id`          : 由 (title, url) 等字段生成的稳定标识（`Utils.make_id`）
- `title`       : 职位标题
- `position`    : 职位类型
- `posted_at`   : 发布日期（`YYYY-MM-DD`，若站点给到则规范化）
- `deadline`    : 截止日期（`YYYY-MM-DD`，若站点给到则规范化）
- `url`         : 职位详情页链接
- `status`      : `"open"` 或 `"closed"`
- `scraped_at`  : 抓取时间（UTC ISO8601，绝对时间；由 `storage.now_iso()` 生成）
- （聚合网站爬虫可额外补充 `school`、`country` 字段；缺失时在 LLM 抽取阶段尝试补全，证据不足则 `"NaN"`）

**示例：**

```
{
"id": "c0ffee1234abcd",
"title": "Doctoral student in Physics",
"position": "Doctoral student",
"posted_at": "2025-09-10",
"deadline": "2025-10-15",
"url": "https://example.varbi.com/whatnot
",
"status": "open",
"scraped_at": "2025-09-23T12:34:56Z"
}

````

### （新增）项目制（Program）数据模型（精简六字段）

项目记录仅保留以下字段，其他字段统一为 `""`：

`id`、`title`、`position`、`url`、`status`、`scraped_at`、`deadline`、`posted_at`

**示例：**



```

{
"id": "b16a1f7e0f2d9a9c",
"title": "Graduate School of XYZ — PhD Program",
"position": "PhD Program",
"url": "https://example.edu/gradschool/phd-program
",
"status": "open",
"scraped_at": "2025-10-14T12:34:56Z"
"deadline": "",
"posted_at": ""
}

```

---

## 运行方式

### 1) 安装依赖（示例）

```

pip install requests beautifulsoup4 pandas selenium

# 如需本地 LLM 抽取，请按需安装 transformers/accelerate/bitsandbytes 等

```

### 2) 运行指定国家（以瑞典 sweden 为例）



```

python run.py

```



运行输出：


* `data/<country>/<school>/current.json`：该校当前开放职位（覆盖写入）

* `data/<country>/<school>/archive.json`：该校历史关闭职位（追加）

* `results/report\_YYYY-MM-DD.json`：本次运行的国家级汇总报告



### （新增）运行项目制（Program）



在 `scrapers/<country>/\_\_init\_\_.py` 中添加：



```

all_prog = ["<schoolProg1>", "<schoolProg2>", ...]

```




运行结果：

* 各国岗位与项目报告分别保存在 `results/<country>/` 与 `results/<country>_Prog/`；
* 生成总汇总报告：

  * 岗位：`results/report_all_YYYY-MM-DD.json`
  * 项目：`results/report_all_YYYY-MM-DD_Prog.json`
  * 岗位 + 项目合并：`results/report_all_YYYY-MM-DD_Full.json`

---

## 入口脚本（run.py）行为

* 自动导入 `scrapers.<country>` 包，读取 `__all__` 中的学校列表
* 依次 `import scrapers.<country>.<school>` 并调用 `fetch()`
* 使用 `core.diff.diff_and_update()` 按 `title` 查重与增量更新：
  * 新职位：加入 `current.json`
  * 已有职位：以“**非空覆盖**”策略更新字段
  * 本次缺失的旧职位：标记为 `closed` 并追加到 `archive.json`
* 任何一个学校失败不会阻断其他学校，错误会记录到 `results/report_*.json`

### （新增）批量运行与计时功能

* `run_all_countries()`：遍历 `scrapers/` 下所有国家，逐国运行岗位


