# Oversea-Job-Searching-Platform



本项目用于\*\*每日自动\*\*爬取全球School官网与第三方岗位聚合网站发布的\*\*岗位与项目\*\*，并以\*\*统一数据模型\*\*进行本地存储与\*\*增量更新\*\*。  

系统强调：\*\*一次入口\*\*、\*\*按国家批量\*\*、\*\*每校独立爬虫\*\*、\*\*通用去重与归档\*\*、\*\*错误不阻断整体运行\*\*、\*\*静态/动态页面自适配\*\*、\*\*本地 LLM 批处理抽取\*\*。



---



\## 目录结构



```



.

|-- core/                 # 核心通用模块

|   |-- utils.py          # 工具函数（日期处理、ID 生成、规范化、博士岗判定、Selenium 基础封装：驱动创建、打开页面、等待、点击、滚动）

|   |-- storage.py        # JSON 读写、UTC 时间戳（now\_iso）

|   |-- diff.py           # 增量更新（查重/合并/归档写入统计）

|   `-- non\_phd.py        # 非博士岗位收集与存储（追加、批量、收集器）

| |-- scrapers/             # 各国/学校爬虫（每个学校一个文件，暴露 fetch()） |   `-- sweden/

|       |-- \*\*init\*\*.py   # 列出该国家的学校清单

|       |-- lund.py

|       |-- gothenburg.py

|       |-- karolinska.py

|       `-- uppsala.py

| |-- data/                 # 爬取结果（每校一个目录） |   `-- sweden/

|       |-- lund/

|       |   |-- current.json

|       |   |-- archive.json

|       |   `-- non\_phd\_candidates.json

|-- data\_web/             # 第三方岗位聚合网站抓取结果（每站一个目录）

|   `-- academic\_transfer\_web/ |       |-- current.json |       `-- archive.json

|   `-- academic\_positions\_web/ |       |-- current.json |       `-- archive.json

|

|-- data\_llm/             # LLM 抽取后的结构化结果（镜像 data/\*\* 的层级）

|   `-- sweden/ |       |-- lund/ |       |   |-- current.json |       |   `-- archive.json

|       `-- ...

| |-- results/              # 每次运行的汇总报告（JSON） |   |-- report\_YYYY-MM-DD.json |   |-- report\_YYYY-MM-DD\_Prog.json |   |-- report\_all\_YYYY-MM-DD.json |   |-- report\_all\_YYYY-MM-DD\_Prog.json |   |-- report\_all\_YYYY-MM-DD\_Full.json |   `-- runtime\_log.jsonl

|

|-- tool/

|   |-- page\_chat1.py     # 智能抓正文（requests→Selenium 兜底）\& 本地 LLM 对话封装

|   `-- job\_llm\_cron.py   # （或 job\_llm\_batch.py）批处理字段抽取 → 写入 data\_llm/\*\*

| |-- scraper\_jobweb/       # 聚合网站爬虫  |   `-- job\_web/

|       |-- academic\_transfer\_web.py

|       `-- academic\_positions\_web.py

| |-- run.py                # 入口脚本：按国家自动发现并运行所有学校爬虫；支持项目、聚合网站与全量运行

`-- README.md



````





---



\## 数据模型（统一字段）



\### 职位（Position）



每个职位是一条 JSON 记录：



\- `id`          : 由 (title, url) 等字段生成的稳定标识（`Utils.make\_id`）

\- `title`       : 职位标题

\- `position`    : 职位类型

\- `posted\_at`   : 发布日期（`YYYY-MM-DD`，若站点给到则规范化）

\- `deadline`    : 截止日期（`YYYY-MM-DD`，若站点给到则规范化）

\- `url`         : 职位详情页链接

\- `status`      : `"open"` 或 `"closed"`

\- `scraped\_at`  : 抓取时间（UTC ISO8601，绝对时间；由 `storage.now\_iso()` 生成）

\- （聚合网站爬虫可额外补充 `school`、`country` 字段；缺失时在 LLM 抽取阶段尝试补全，证据不足则 `"NaN"`）



\*\*示例：\*\*

```

{

&nbsp; "id": "c0ffee1234abcd",

&nbsp; "title": "Doctoral student in Physics",

&nbsp; "position": "Doctoral student",

&nbsp; "posted\_at": "2025-09-10",

&nbsp; "deadline": "2025-10-15",

&nbsp; "url": "https://example.varbi.com/whatnot",

&nbsp; "status": "open",

&nbsp; "scraped\_at": "2025-09-23T12:34:56Z"

}

````



\### （新增）项目制（Program）数据模型（精简六字段）



项目记录仅保留以下字段，其他字段统一为 `""`：



`id`、`title`、`position`、`url`、`status`、`scraped\_at`、`deadline`、`posted\_at`



\*\*示例：\*\*



```

{

&nbsp; "id": "b16a1f7e0f2d9a9c",

&nbsp; "title": "Graduate School of XYZ — PhD Program",

&nbsp; "position": "PhD Program",

&nbsp; "url": "https://example.edu/gradschool/phd-program",

&nbsp; "status": "open",

&nbsp; "scraped\_at": "2025-10-14T12:34:56Z"

&nbsp; "deadline": "",

&nbsp; "posted\_at": ""

}

```



---



\## 运行方式



\### 1) 安装依赖（示例）



```

pip install requests beautifulsoup4 pandas selenium

\# 如需本地 LLM 抽取，请按需安装 transformers/accelerate/bitsandbytes 等

```



\### 2) 运行指定国家（以瑞典 sweden 为例）



```

python run.py

```



运行输出：



\* `data/<country>/<school>/current.json`：该校当前开放职位（覆盖写入）

\* `data/<country>/<school>/archive.json`：该校历史关闭职位（追加）

\* `results/report\_YYYY-MM-DD.json`：本次运行的国家级汇总报告



\### （新增）运行项目制（Program）



在 `scrapers/<country>/\_\_init\_\_.py` 中添加：



```

\_\_all\_prog\_\_ = \["<schoolProg1>", "<schoolProg2>", ...]

```



调用你已实现的入口（示例）：



```

from run import run\_country\_Prog

run\_country\_Prog("<country>")

```



运行输出（与岗位分开）：



\* `data/<country>/<schoolProg>/current.json`

\* `data/<country>/<schoolProg>/archive.json`

\* `results/report\_YYYY-MM-DD\_Prog.json`



\### （新增）一次性运行所有国家



可使用统一入口函数批量运行所有国家的爬虫。



\* 运行所有国家的职位（Position）：



```

from run import run\_all\_countries

run\_all\_countries()

```



\* 运行所有国家的项目（Program）：



```

from run import run\_all\_countries\_Prog

run\_all\_countries\_Prog()

```



\* 一次性运行所有国家的岗位 + 项目：



```

from run import run\_all\_countries\_full

run\_all\_countries\_full()

```



\* 带计时与日志：



```

from run import run\_all\_countries\_full\_with\_timer

run\_all\_countries\_full\_with\_timer()

```



运行结果：



\* 各国岗位与项目报告分别保存在 `results/<country>/` 与 `results/<country>\_Prog/`；

\* 生成总汇总报告：



&nbsp; \* 岗位：`results/report\_all\_YYYY-MM-DD.json`

&nbsp; \* 项目：`results/report\_all\_YYYY-MM-DD\_Prog.json`

&nbsp; \* 岗位 + 项目合并：`results/report\_all\_YYYY-MM-DD\_Full.json`



---



\## 入口脚本（run.py）行为



\* 自动导入 `scrapers.<country>` 包，读取 `\_\_all\_\_` 中的学校列表

\* 依次 `import scrapers.<country>.<school>` 并调用 `fetch()`

\* 使用 `core.diff.diff\_and\_update()` 按 `title` 查重与增量更新：

