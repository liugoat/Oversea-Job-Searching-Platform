import hashlib
from datetime import datetime
import pandas as pd
from typing import Optional
import re
import unicodedata

class Utils:
    # --------- Doctoral detection patterns (can be overridden in subclass) ----------
    # 排除：博后/博前（覆盖更多变体）
    # 博后 / 博前排除模式（不再排除 prae-doc）
    DENY_POSTDOC = re.compile(
        r"""
        \b(
            # --- 博后 Postdoc 族 ---
            post\s*[-\s\u2010-\u2015]?doc(?:s|tor(?:al|ate)?)?   # postdoc/post-doc/postdocs/postdoctoral/postdoctorate
          | post\s*[-\s\u2010-\u2015]?doctoral
          | post\s*[-\s\u2010-\u2015]?doctorate
          | post\s*[-\s\u2010-\u2015]?doctor
          | post[\s/\u2010-\u2015-]?doktorand(?:[/\s\u2010-\u2015-]?(?:in|innen|en))?
          | postdok(?:tor(?:and)?)?

            # --- 博前 Predoc（保留真正 predoc，移除 prae-doc）
          | pre\s*[-\s\u2010-\u2015]?doc(?:s)?                     # pre-doc / pre doc / pre-docs
          | predoc(?:s)?                                           # predoc/predocs
          | pre\s*[-\s\u2010-\u2015]?doctoral                      # pre-doctoral / pre doctoral
          | pre\s*[-\s\u2010-\u2015]?doctorate                     # pre-doctorate
          | pre\s*[-\s\u2010-\u2015]?ph\.?\s*D\.?                  # pre-PhD / pre PhD

            # --- 通用 early stage / ESR（通常为 Predoc 项）
          | early\s*[-\s\u2010-\u2015]?stage\s*researcher
          | esr\b
        )\b
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # 严格：仅 “Doctoral student”，且排除 post-doctoral 前缀
    STRICT_ALLOW = re.compile(
        r"(?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s-]*student\b",
        re.IGNORECASE
    )

    # 宽松博士岗位识别：新增 prae-doc / praedoc
    BROAD_ALLOW = re.compile(
        r"""
        (
            (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*student\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*position\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*researcher\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*candidate\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*fellow\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*trainee\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*studentship\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral[\s/–—-]*scholarship\b
          | \bdoctorate\b
          | \bthird[\s/–—-]*cycle\b
          | (?<!post)(?<!post[-/\s\u2010-\u2015])\bdoktorand\b
          | \bph\.?\s*d\.?\b
          | \bphd(?:[\s/–—-]*(student|position|candidate|researcher|fellow|trainee|studentship|scholarship))?\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral(?:\s*/\s*|\s+or\s+)project[\s/–—-]*researcher\b
          | (?<!post)(?<!post[-\s\u2010-\u2015])\bdoctoral\b
          | \bprae\s*[-\s\u2010-\u2015]?doc(?:s)?\b        # ✅ prae-doc/praedoc 作为博士岗位
          | \bpraedoc(?:s)?\b
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    GERMAN_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bpromotionsstelle\b                      # Promotion position
          | \bpromotionsstudium\b                     # doctoral study
          | \bdoktorand(?:in|en|innen)?\b             # Doktorand/in/en/innen
          | \bdissertationsstelle\b                   # dissertation position
          | \bzur\s+promotion\b                       # for a PhD
          | \bmit\s+der\s+möglichkeit\s+zur\s+promotion\b  # with the possibility to pursue a PhD
          | \bprae\s*[-\s\u2010-\u2015]?doc(?:s)?\b  # prae-doc/praedoc
          | \bpraedoc(?:s)?\b
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    DUTCH_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bpromovend(?:us|i|a|en)?\b             # promovendus / promovendi / promovenda / promovenden
          | \bpromotie[\s-]?(onderzoeker|positie|studie|traject)\b  # promotieonderzoeker 等
          | \baio\b                                 # AIO = Assistent in Opleiding
          | \bphd['’]?\s*er\b                       # PhD'er / PhD’er
          | \bdoctoraats(student|positie|opleiding)\b  # doctoraatsstudent 等
          | \bonderzoeker\s+in\s+opleiding\b        # onderzoeker in opleiding
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    CZECH_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bdoktorand(?:ka|ky|i|ů)?\b                         # doktorand / doktorandka / doktorandi / doktorandů
          | \bstudent(?:ka|i)?\s+doktorsk(?:ého|eho|y|e)\s+studia\b   # student doktorského studia（含无重音变体）
          | \bdoktorsk(?:é|e)\s+studium\b                       # doktorské studium
          | \bph\.?\s*d\.?\b                                    # Ph.D. / PhD
          | \bdoktorské\s+studium\s*\(?\s*ph\.?\s*d\.?\s*\)?\b  # doktorské studium (Ph.D.)
          | \bdoktorské\b                                       # 保守匹配：单独“doktorské”
          | \bdiserta[čc]n[ií]\s+pr[aá]ce\b                     # disertační práce（篇章里常见）
          | \bpostup\s+k\s+z[ií]sk[aá]n[ií]\s+titul[uů]?\s*ph\.?\s*d\.?\b # 获得 Ph.D. 的措辞
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    FRENCH_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bdoctorant(?:e|\.?e|·e)?s?\b                        # doctorant / doctorante / doctorant·e(s)
          | \bth[ée]se\s+de\s+doctorat\b                         # thèse de doctorat
          | \bcontrat(?:\s+de)?\s+doctoral\b                     # contrat doctoral
          | \bprogramme\s+doctoral\b                             # programme doctoral
          | \b[ée]cole\s+doctorale\b                             # école doctorale
          | \bchercheur(?:se)?\s+doctoral(?:e)?s?\b              # chercheur(se) doctoral(e)
          | \bph\.?\s*d\.?\b                                     # PhD / Ph.D.
          | \bdoctorat\b                                         # doctorat
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # 放在类里，与其它 *_ALLOW 并列
    SWEDISH_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bdoktorand(?:er|erna|en)?\b                     # doktorand / doktorander / doktoranden / doktoranderna
          | \bindustridoktorand(?:er|erna|en)?\b             # industridoktorand（工业博士生）
          | \bdoktorandanst[aä]llning(?:ar|en)?\b            # doktorandanställning / -ar / -en
          | \bdoktorandtj[aä]nst(?:er|en)?\b                 # doktorandtjänst / -er / -en
          | \bdoktorandplats(?:er|en)?\b                     # doktorandplats / -er / -en
          | \bforskarutbildning(?:en)?\b                     # forskarutbildning（博士教育）
          | \bdoktorsprogram(?:met|men)?\b                   # doktorsprogram / -met / -men
          | \bdoktorsutbildning(?:en)?\b                     # doktorsutbildning
          | \bforskarskola(?:n|or|orna)?\b                   # forskarskola（博士生院/研究生院）
          | \bantagen(?:e|a)?\s+(till|som)\s+doktorand\b     # 被录取为博士生/录取到博士学习
          | \bantagning\s+till\s+forskarutbildning\b         # 博士教育录取
          | \bph\.?\s*d\.?\b                                 # PhD / Ph.D. 兜底
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # 放在你的类里，与其它 *_ALLOW 并列
    SPANISH_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bdoctorand[oa]s?\b                              # doctorando / doctoranda / doctorandos / doctorandas
          | \bestudiante(?:s)?\s+de\s+doctorado\b            # estudiante(s) de doctorado
          | \bprograma\s+de\s+doctorado\b                    # programa de doctorado
          | \bestudios\s+de\s+doctorado\b                    # estudios de doctorado
          | \bescuela\s+de\s+doctorado\b                     # escuela de doctorado
          | \bph\.?\s*d\.?\b                                 # PhD / Ph.D.
          | \bdoctorado\b                                    # doctorado（兜底，但见下方 posdoc/predoc 排除）
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    # 挪威语博士岗位关键词
    NORWEGIAN_DOCTORAL_ALLOW = re.compile(
        r"""
        (
            \bstipendiat(?:er|ene|stilling(?:er)?|en)?\b            # stipendiat / stipendiatstilling(er)
          | \bdoktorgrads(?:stipendiat|student|kandidat|program|studium|utdanning)\b
          | \bdoktorgrad\b
          | \bforskerutdanning\b                                   # 研究者教育（博士教育语境）
          | \bph\.?\s*d\.?\b                                       # PhD / Ph.D.
          | \bph\.?\s*d\.?\s*[-–—/]?\s*(stipendiat|kandidat|student|stilling|program|studium)\b
          | \bopptak\s+til\s+(ph\.?\s*d\.?|doktorgradsutdanning)\b # “录取到 PhD/博士教育”
        )
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    @classmethod
    def _is_german_doctoral_title(cls, title: str) -> bool:
        """辅助函数：德语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()
        # 先排除常见博后词汇
        if re.search(r"\bpost[\s-]?(doc|doktor|doktorand|doctoral)\b", t):
            return False
        return bool(cls.GERMAN_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_dutch_doctoral_title(cls, title: str) -> bool:
        """辅助函数：荷兰语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()
        # 先排除 postdoc 等博后
        if re.search(r"\bpost[\s-]?(doc|doctoral|doctor|doctorand)\b", t):
            return False
        return bool(cls.DUTCH_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_czech_doctoral_title(cls, title: str) -> bool:
        """辅助函数：捷克语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()
        # 先排除 postdoc / predoc 等（沿用你的排除表）
        if cls.DENY_POSTDOC.search(t):
            return False
        return bool(cls.CZECH_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_french_doctoral_title(cls, title: str) -> bool:
        """辅助函数：法语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()

        # 先排除法语常见博后写法（在 DENY_POSTDOC 之外再做一道保险）
        # postdoctorant(e)/post-doctorant(e), postdoctorat, post-doctoral 等
        if (
                cls.DENY_POSTDOC.search(t)
                or re.search(r"\bpost[\s-]?doctor(?:ant(?:e|s)?|at|al)(?:e|s)?\b", t, re.IGNORECASE)
        ):
            return False

        return bool(cls.FRENCH_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_swedish_doctoral_title(cls, title: str) -> bool:
        """辅助函数：瑞典语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()

        # 先排除 postdoc（瑞典语：postdoktor/postdok/postdoktoral 等）
        if cls.DENY_POSTDOC.search(t) or re.search(r"\bpostdok(?:tor(?:al)?)?\b", t, re.IGNORECASE):
            return False

        return bool(cls.SWEDISH_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_spanish_doctoral_title(cls, title: str) -> bool:
        """辅助函数：西班牙语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()

        # 先排除：posdoc/posdoctoral/posdoctorado + 你已有的 DENY_POSTDOC（含 predoc）
        if (
                cls.DENY_POSTDOC.search(t)
                or re.search(r"\bpos(?:t)?doc(?:tor(?:al|ado)?)?\b", t,
                             re.IGNORECASE)  # posdoc / postdoc / posdoctoral / posdoctorado
                or re.search(r"\binvestigador(?:a)?\s+pos(?:t)?doctoral\b", t, re.IGNORECASE)
        ):
            return False

        return bool(cls.SPANISH_DOCTORAL_ALLOW.search(t))

    @classmethod
    def _is_norwegian_doctoral_title(cls, title: str) -> bool:
        """辅助函数：挪威语博士岗位判定。"""
        if not title:
            return False
        t = title.lower()

        # 先排除挪威语常见博后（postdoktor / postdoc / postdoktoral 等）
        if cls.DENY_POSTDOC.search(t) or re.search(r"\bpostdoktor(?:al)?\b", t, re.IGNORECASE):
            return False

        return bool(cls.NORWEGIAN_DOCTORAL_ALLOW.search(t))

    @staticmethod
    def make_id(*parts) -> str:
        """基于任意字段生成稳定 id"""
        base = "::".join([str(p).strip().lower() for p in parts if p])
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    @staticmethod
    def coerce_date(s: str, fmts=None) -> Optional[str]:
        """
        将常见日期字符串规范化为 YYYY-MM-DD。
        - 接口与参数保持不变
        - 先用明确格式匹配，再用 pandas 兜底（分别以 dayfirst=False/True 尝试，避免 UserWarning）
        """
        if not s or not isinstance(s, str):
            return None

        s = s.strip()
        # 1) 明确格式优先（在你原有基础上，补充常见欧式/斜杠写法）
        fmts = fmts or [
            "%Y-%m-%d",  # ISO
            "%d %b %Y", "%d %B %Y", "%d %b, %Y",
            "%d.%m.%Y",  # 欧式: 14.10.2025 / 01.11.2025
            "%m/%d/%Y",  # 美式: 10/31/2025
            "%d/%m/%Y",  # 欧式: 31/10/2025
        ]
        for f in fmts:
            try:
                return datetime.strptime(s, f).strftime("%Y-%m-%d")
            except Exception:
                continue

        # 2) pandas 兜底：先按 dayfirst=False（美式/ISO），再 dayfirst=True（欧式）
        try:
            dt = pd.to_datetime(s, errors="coerce", dayfirst=False)
            if pd.notna(dt):
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        try:
            dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
            if pd.notna(dt):
                return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

        return None

    # NEW: 核心封装——博士生岗位标题判定
    @classmethod
    def is_doctoral_title(cls, title: str, *, mode: str = "strict") -> bool:
        """
        基于标题判定是否为博士生（非博后）岗位。
        """
        if not title or not isinstance(title, str):
            return False

        # Step 1️⃣：德语特判（优先，因为很多德语岗位不含“doctoral/PhD”）
        if cls._is_german_doctoral_title(title):
            return True

        # Step 1.5️：荷兰语特判
        if cls._is_dutch_doctoral_title(title):
            return True

        # 1.75) 捷克语（新增）
        if cls._is_czech_doctoral_title(title):
            return True

        # Step 1.8️⃣：法语（✅ 新增）
        if cls._is_french_doctoral_title(title):
            return True

        # 1.81 瑞典语（新增）
        if cls._is_swedish_doctoral_title(title):
            return True

        # 1.82 西班牙语（新增）
        if cls._is_spanish_doctoral_title(title):
            return True

        # 1.83 挪威语 ✅（新增）
        if cls._is_norwegian_doctoral_title(title):
            return True

        # Step 2️⃣：英文路径
        allow = cls.STRICT_ALLOW if mode == "strict" else cls.BROAD_ALLOW
        if allow.search(title):
            return True

        # Step 3️⃣：排除 postdoc
        if cls.DENY_POSTDOC.search(title):
            return False

        # Step 4️⃣：默认否
        return False

    # NEW: 文本规范化（lower/collapse spaces 等）
    @staticmethod
    def normalize(s: str, *, lower: bool = True, collapse_spaces: bool = True, nf: str = "NFKC") -> str:
        """
        规范化文本：Unicode 归一化、替换特殊空格/破折号、折叠空白、可选小写化。
        主要用于标题/去重键的标准化（非展示用）。
        """
        if s is None:
            return ""
        if not isinstance(s, str):
            s = str(s)

        # 1) Unicode 归一化（兼容全角/兼容字符）
        s = unicodedata.normalize(nf, s)

        # 2) 统一特殊空格与破折号
        #    - 空格：NBSP/THIN SPACE/NARROW NBSP -> 普通空格
        s = (
            s.replace("\u00A0", " ")
             .replace("\u2009", " ")
             .replace("\u202F", " ")
        )
        #    - 破折号族 → 连字符 '-'
        dash_table = {ord(c): "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"}
        s = s.translate(dash_table)

        # 3) 折叠所有空白为单空格
        if collapse_spaces:
            s = re.sub(r"\s+", " ", s, flags=re.UNICODE)

        # 4) 去首尾空白
        s = s.strip()

        # 5) 小写化（用于去重/对比；若用于展示，可传 lower=False）
        if lower:
            s = s.lower()

        return s

    # === 直接加入到 Utils 类中 ===

    @staticmethod
    def selenium_make_driver(
            browser: str = "auto",  # "chrome" | "edge" | "auto"
            headless="new",  # True | False | "new" | "old"
            binary_path: Optional[str] = None,  # 浏览器可执行文件路径（可选）
            driver_path: Optional[str] = None,  # 驱动可执行文件路径（可选）
            use_manager: bool = False,  # 兜底用 webdriver-manager（需安装）
            window_size: tuple = (1920, 1080),
    ):
        """
        仅创建并返回 WebDriver，不打开页面。
        - 优先用指定 driver_path，其次 PATH，之后 Selenium Manager，最后（可选）webdriver-manager
        - headless 优先 '--headless=new' 不支持时自动回退 '--headless'
        """
        import shutil
        from contextlib import suppress
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException

        def _options(kind: str):
            if kind == "chrome":
                from selenium.webdriver.chrome.options import Options as ChromeOptions
                opts = ChromeOptions()
            else:
                from selenium.webdriver.edge.options import Options as EdgeOptions
                opts = EdgeOptions()

            # headless
            if headless in (True, "new"):
                opts.add_argument("--headless=new")
            elif headless in ("old",):
                opts.add_argument("--headless")
            elif headless is True:
                opts.add_argument("--headless")

            # 通用稳态参数
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
            if binary_path:
                with suppress(Exception):
                    opts.binary_location = binary_path
            return opts

        def _start(kind: str):
            if kind == "chrome":
                from selenium.webdriver.chrome.service import Service as ChromeService
                Service = ChromeService
                starter = lambda service, options: webdriver.Chrome(service=service, options=options)
                names = ("chromedriver", "chromedriver.exe")
            else:
                from selenium.webdriver.edge.service import Service as EdgeService
                Service = EdgeService
                starter = lambda service, options: webdriver.Edge(service=service, options=options)
                names = ("msedgedriver", "msedgedriver.exe")

            opts = _options(kind)
            for attempt in ("primary", "fallback_old_headless"):
                try:
                    # 1) 指定驱动路径
                    if driver_path:
                        return starter(Service(driver_path), opts)
                    # 2) PATH
                    exe = None
                    for n in names:
                        exe = exe or shutil.which(n)
                    if exe:
                        return starter(Service(exe), opts)
                    # 3) Selenium Manager
                    with suppress(Exception):
                        return starter(None, opts)
                    # 4) webdriver-manager
                    if use_manager:
                        if kind == "chrome":
                            from webdriver_manager.chrome import ChromeDriverManager
                            drv = ChromeDriverManager().install()
                        else:
                            from webdriver_manager.microsoft import EdgeChromiumDriverManager
                            drv = EdgeChromiumDriverManager().install()
                        return starter(Service(drv), opts)
                except WebDriverException as e:
                    msg = str(e).lower()
                    if attempt == "primary" and (
                            "headless=new" in msg or "unknown option" in msg or "invalid argument" in msg):
                        # 回退旧 headless
                        nonlocal headless
                        headless = "old"
                        opts = _options(kind)
                        continue
                    raise
            raise RuntimeError(f"Failed to start {kind} WebDriver")

        last_err = None
        kinds = ["chrome", "edge"] if browser == "auto" else [browser]
        for kind in kinds:
            try:
                return _start(kind)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"Unable to start WebDriver ({browser}). Last error: {last_err}")

    @staticmethod
    def selenium_open(
            url: str,
            browser: str = "auto",
            headless="new",
            binary_path: Optional[str] = None,
            driver_path: Optional[str] = None,
            use_manager: bool = False,
            window_size: tuple = (1920, 1080),
            page_load_timeout: int = 60,
    ):
        """
        创建 WebDriver 并打开 URL。返回 driver（调用方负责 driver.quit()）。
        只做“打开页面”这一步，后续操作由调用方自行完成。
        """
        driver = Utils.selenium_make_driver(
            browser=browser,
            headless=headless,
            binary_path=binary_path,
            driver_path=driver_path,
            use_manager=use_manager,
            window_size=window_size,
        )
        driver.set_page_load_timeout(page_load_timeout)
        driver.get(url)
        return driver

    @staticmethod
    def selenium_wait(
            driver,
            css: Optional[str] = None,
            xpath: Optional[str] = None,
            cond: str = "presence",  # "presence" | "visible" | "clickable" | "all"
            timeout: int = 20,
    ):
        """
        基本等待封装：等待元素出现/可见/可点击。
        - cond="presence": 返回单个 WebElement
        - cond="visible" : 返回单个 WebElement（可见）
        - cond="clickable": 返回单个 WebElement（可点）
        - cond="all"     : 返回 WebElement 列表（存在即可）
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        if not (css or xpath):
            raise ValueError("css 或 xpath 至少提供一个")
        locator = (By.CSS_SELECTOR, css) if css else (By.XPATH, xpath)

        if cond == "presence":
            return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))
        elif cond == "visible":
            return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(locator))
        elif cond == "clickable":
            return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
        elif cond == "all":
            return WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located(locator))
        else:
            raise ValueError(f"未知 cond: {cond}")

    @staticmethod
    def selenium_click(
            driver,
            css: Optional[str] = None,
            xpath: Optional[str] = None,
            timeout: int = 20,
            scroll_into_view: bool = True,
    ):
        """
        等待元素可点击后进行点击；默认先滚动到视区内，返回被点击的元素。
        """
        el = Utils.selenium_wait(driver, css=css, xpath=xpath, cond="clickable", timeout=timeout)
        if scroll_into_view:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            except Exception:
                pass
        el.click()
        return el

    @staticmethod
    def selenium_scroll(
            driver,
            mode: str = "end",  # "end" | "top" | "px" | "element"
            px: int = 0,  # mode="px" 时使用
            css: Optional[str] = None,  # mode="element" 时可用
            xpath: Optional[str] = None,  # mode="element" 时可用
            max_scroll: int = 10,
            pause: float = 0.8,
    ):
        """
        基础滚动：
          - end    : 多次滚动到底，检测高度不变即停止
          - top    : 回到顶部
          - px     : 垂直滚动指定像素（正向下/负向上）
          - element: 滚动某元素到视区
        """
        import time
        from selenium.webdriver.common.by import By

        if mode == "top":
            driver.execute_script("window.scrollTo(0, 0);")
            return
        if mode == "px":
            driver.execute_script("window.scrollBy(0, arguments[0]);", int(px))
            return
        if mode == "element":
            if not (css or xpath):
                raise ValueError("mode='element' 需要提供 css 或 xpath")
            el = driver.find_element(By.CSS_SELECTOR, css) if css else driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            return
        # 默认：滚动到底（懒加载）
        last_h = 0
        for _ in range(max_scroll):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)
            new_h = driver.execute_script("return document.body.scrollHeight")
            if new_h == last_h:
                break
            last_h = new_h


# 允许以后自定义扩展：
class CustomUtils(Utils):
    """不同学校/国家可以继承 Utils，覆盖 coerce_date/make_id/正则模式"""
    pass
