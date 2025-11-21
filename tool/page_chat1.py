# -*- coding: utf-8 -*-
"""
page_chat1.py — URL优先、强提示、智能抓取（requests 优先，动态判定后 Selenium 兜底）
依赖：pip install requests beautifulsoup4 transformers torch
如需4/8bit量化：pip install bitsandbytes
"""

import time
from typing import Optional, Tuple, List, Dict
from core.utils import Utils  # 复用你项目的 Selenium 封装

import sys, re
import requests
from bs4 import BeautifulSoup

# --- 保证控制台能立刻看到输出 ---
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass

DEFAULT_MODEL_PATH = r"F:/llm/Qwen2.5-1.5B-Instruct"

# ========== 本地模型（显存友好版） ==========
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# 可选量化
try:
    from transformers import BitsAndBytesConfig
    _HAS_BNB = True
except Exception:
    _HAS_BNB = False


class LocalLLM:
    """
    更稳健的加载器：
    - 自动区分 GPU / CPU：
        * GPU 可用 -> device_map="auto"
        * GPU 不可用 -> device_map={"": "cpu"}
    - 仅在 GPU 可用时允许 4bit 量化（需要 bitsandbytes）
    - 使用 dtype= 参数（替代 torch_dtype）
    """
    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        *,
        load_in_4bit: bool = False,          # 仅 GPU 可用时生效
        dtype: str | torch.dtype = "auto",   # "auto" | "float16" | "bfloat16" | "float32" | torch.dtype
        max_input_tokens: int = 6000,
        max_new_tokens_default: int = 800,
    ):
        print(f"[INIT] 加载本地模型：{model_path}", flush=True)
        self.tok = AutoTokenizer.from_pretrained(
            model_path, trust_remote_code=True, use_fast=True
        )

        use_cuda = torch.cuda.is_available()
        device_map = "auto" if use_cuda else {"": "cpu"}

        # 量化配置（仅 GPU 下启用）
        quant_cfg = None
        if load_in_4bit and use_cuda:
            try:
                from transformers import BitsAndBytesConfig
                # 4bit 通用配置；你也可以按需再调 bnb_4bit_quant_type 等
                quant_cfg = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                )
                print("[INIT] 使用 4-bit 量化 (bitsandbytes)。", flush=True)
            except Exception as e:
                print(f"[WARN] 未安装 bitsandbytes 或初始化失败，改为非量化: {e}", flush=True)
                quant_cfg = None

        # dtype 处理
        resolved_dtype = None
        if dtype != "auto":
            resolved_dtype = getattr(torch, dtype) if isinstance(dtype, str) else dtype

        # 组装 from_pretrained 的 kwargs
        fp_kwargs = dict(
            device_map=device_map,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        if quant_cfg is not None:
            fp_kwargs["quantization_config"] = quant_cfg
        if resolved_dtype is not None:
            fp_kwargs["dtype"] = resolved_dtype

        # 实例化模型
        self.m = AutoModelForCausalLM.from_pretrained(model_path, **fp_kwargs)


        self.eos = self.tok.eos_token_id
        self.max_input_tokens = max_input_tokens
        self.max_new_tokens_default = max_new_tokens_default
        print("[INIT] 模型加载完成。", flush=True)

    def _trim(self, text: str, max_tokens: int) -> str:
        ids = self.tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"][0]
        if ids.size(0) <= max_tokens:
            return text
        ratio = max_tokens / float(ids.size(0))
        cut = max(1000, int(len(text) * ratio))
        return text[:cut]

    def chat(self, messages: List[Dict], max_new_tokens=None, temperature=0.2, top_p=0.9) -> str:
        if max_new_tokens is None:
            max_new_tokens = self.max_new_tokens_default

        joined = "\n".join([m.get("content","") for m in messages if isinstance(m.get("content",""), str)])
        ids = self.tok(joined, return_tensors="pt", add_special_tokens=False)["input_ids"][0]
        if ids.size(0) > self.max_input_tokens:
            for m in messages:
                if "<DOC>" in m.get("content",""):
                    m["content"] = self._trim(m["content"], self.max_input_tokens // 2)
                    break

        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tok(prompt, return_tensors="pt")
        # 把 inputs 放到跟模型一致的设备
        dev = next(self.m.parameters()).device
        inputs = {k: v.to(dev) for k, v in inputs.items()}

        input_len = inputs["input_ids"].shape[1]
        with torch.no_grad():
            out = self.m.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=(temperature is not None),
                temperature=temperature, top_p=top_p,
                eos_token_id=self.eos
            )[0]
        gen = out[input_len:]
        return self.tok.decode(gen, skip_special_tokens=True).strip()



    def _trim(self, text: str, max_tokens: int) -> str:
        ids = self.tok(text, return_tensors="pt", add_special_tokens=False)["input_ids"][0]
        if ids.size(0) <= max_tokens:
            return text
        ratio = max_tokens / float(ids.size(0))
        cut = max(2000, int(len(text) * ratio))
        return text[:cut]

    def chat(self, messages: List[Dict], max_new_tokens=None, temperature=0.2, top_p=0.9) -> str:
        joined = "\n".join([m.get("content","") for m in messages if isinstance(m.get("content",""), str)])
        ids = self.tok(joined, return_tensors="pt", add_special_tokens=False)["input_ids"][0]
        if ids.size(0) > self.max_input_tokens:
            for m in messages:
                if "<DOC>" in m.get("content",""):
                    m["content"] = self._trim(m["content"], int(self.max_input_tokens * 0.7))
                    break
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tok(
            prompt,
            return_tensors="pt",
            truncation=True,              # 二次兜底
            max_length=self.max_input_tokens,
        ).to(self.m.device)
        input_len = inputs["input_ids"].shape[1]
        gen_len = min(max_new_tokens if max_new_tokens is not None else self.max_new_tokens_default, 192)
        with torch.inference_mode():
            out = self.m.generate(
                **inputs,
                max_new_tokens=gen_len,
                do_sample=(temperature is not None),
                temperature=temperature, top_p=top_p,
                eos_token_id=self.eos
            )[0]
        gen = out[input_len:]
        return self.tok.decode(gen, skip_special_tokens=True).strip()


# ========== 抓正文（requests → 动态判定 → Selenium 兜底） ==========
def fetch_page_text(url: str, *, min_len_for_requests: int = 120,
                    selenium_wait_css: Optional[str] = None) -> str:
    print(f"[FETCH] 抓取页面（requests）：{url}", flush=True)
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36")
    }
    raw_html = ""
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or r.encoding
        raw_html = r.text or ""
    except Exception as e:
        print(f"[WARN] requests 抓取失败：{e}", flush=True)

    text_requests = _html_to_text(raw_html) if raw_html else ""
    print(f"[FETCH] requests 正文≈{len(text_requests):,} 字符。", flush=True)

    need_selenium = _is_likely_dynamic(raw_html, len(text_requests), min_len=min_len_for_requests)

    if not need_selenium:
        if len(text_requests) < 80:
            print("[WARN] 正文较短，但未触发动态判定（可调高 min_len_for_requests）。", flush=True)
        return text_requests

    print("[INFO] 判定为动态页面或正文不足，切换 Selenium 兜底…", flush=True)
    html_s, text_s = _fetch_with_selenium(
        url, wait_css=selenium_wait_css, timeout=40, max_scroll=14, pause=0.8
    )
    return text_s if len(text_s) >= len(text_requests) else text_requests


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.extract()
    for sel in ["header","nav","footer",".footer","#footer",".nav","#nav",".cookie","#cookie"]:
        for t in soup.select(sel):
            t.extract()
    text = soup.get_text("\n", strip=True)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)[:200000]


def _is_likely_dynamic(raw_html: str, text_len: int, *, min_len: int = 120) -> bool:
    if not raw_html:
        return True
    h = (raw_html or "").lower()
    if text_len < min_len:
        return True
    spa_markers = ('id="__next"', 'id="app"', 'id="root"', 'data-reactroot', 'ng-app', '__nuxt', 'id="__nuxt"', 'v-cloak')
    if any(m in h for m in spa_markers) and text_len < 600:
        return True
    bad_signals = ("enable javascript", "please enable javascript", "requires javascript", "loading...", "is-loading", "spinner", "skeleton")
    if any(m in h for m in bad_signals) and text_len < 600:
        return True
    return False


def _fetch_with_selenium(url: str, *, wait_css: Optional[str] = None,
                         timeout: int = 30, max_scroll: int = 12, pause: float = 0.8) -> Tuple[str, str]:
    driver = None
    try:
        print(f"[FETCH][SELENIUM] 打开页面：{url}", flush=True)
        driver = Utils.selenium_open(url, headless="new", page_load_timeout=timeout)

        try:
            if wait_css:
                Utils.selenium_wait(driver, css=wait_css, cond="visible", timeout=timeout)
            else:
                Utils.selenium_wait(driver, css="body", cond="visible", timeout=timeout)
        except Exception:
            pass

        Utils.selenium_scroll(driver, mode="end", max_scroll=max_scroll, pause=pause)
        time.sleep(0.3)
        html = driver.page_source or ""
        text = _html_to_text(html)
        print(f"[FETCH][SELENIUM] 完成，正文≈{len(text):,} 字符。", flush=True)
        return html, text
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


# ========== REPL（保留；批处理脚本不会调用它） ==========
HELP = """
命令：
  :q                退出
  :clear            清空对话（保留当前文档）
  :url              交互输入新URL并切换
  :new <url>        直接切换到新URL
示例提问：
  请总结以下内容：1.截止日期；2.职位标题；3.学校/国家；4.申请人硕士背景/成绩要求
"""

def make_system_prompt() -> str:
    return ("你必须严格基于文档回答；除非用户明确要求推测。"
            "若信息缺失，请直接说明“未在文档中明确给出”,返回NaN。")

def start_session():
    print(f"[INFO] 本地模型：{DEFAULT_MODEL_PATH}", flush=True)
    llm = LocalLLM(DEFAULT_MODEL_PATH)

    while True:
        first = input("请输入岗位URL（必须以 http(s) 开头）：").strip()
        if first.lower().startswith("http://") or first.lower().startswith("https://"):
            url = first
            break
        print("⚠️ 不是有效URL，请重新输入。", flush=True)

    try:
        doc = fetch_page_text(url)
    except Exception as e:
        print(f"[ERROR] 抓取失败：{e}", flush=True)
        return

    system_msg = {"role": "system", "content": make_system_prompt()}
    doc_msg = {"role": "system", "content": f"<DOC>\n{doc}\n</DOC>"}
    history: List[Dict] = [system_msg, doc_msg]
    current_doc = doc

    print("[READY] 已进入对话模式。输入问题开始，或输入 ':q' 退出。", flush=True)
    print(HELP, flush=True)

    while True:
        try:
            q = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[EXIT] 再见。", flush=True); break
        if not q:
            continue

        if q.lower().startswith("http://") or q.lower().startswith("https://"):
            try:
                doc = fetch_page_text(q)
                current_doc = doc
                history = [system_msg, {"role":"system","content":f"<DOC>\n{doc}\n</DOC>"}]
                print("[READY] 已切换到新文档。", flush=True)
            except Exception as e:
                print(f"[ERROR] 抓取失败：{e}", flush=True)
            continue

        if q in (":q", ":quit", ":exit"):
            print("[EXIT] 已退出。", flush=True); break
        if q == ":clear":
            history = [system_msg, {"role":"system","content":f"<DOC>\n{current_doc}\n</DOC>"}]
            print("[INFO] 对话已清空（文档保留）。", flush=True); continue
        if q == ":url":
            new_url = input("请输入新的URL：").strip()
            if not (new_url.lower().startswith("http://") or new_url.lower().startswith("https://")):
                print("⚠️ 不是有效URL。", flush=True); continue
            try:
                doc = fetch_page_text(new_url)
                current_doc = doc
                history = [system_msg, {"role":"system","content":f"<DOC>\n{doc}\n</DOC>"}]
                print("[READY] 已切换到新文档。", flush=True)
            except Exception as e:
                print(f"[ERROR] 抓取失败：{e}", flush=True)
            continue
        if q.startswith(":new "):
            new_url = q[5:].strip()
            if not (new_url.lower().startswith("http://") or new_url.lower().startswith("https://")):
                print("用法：:new <url>", flush=True); continue
            try:
                doc = fetch_page_text(new_url)
                current_doc = doc
                history = [system_msg, {"role":"system","content":f"<DOC>\n{doc}\n</DOC>"}]
                print("[READY] 已切换到新文档。", flush=True)
            except Exception as e:
                print(f"[ERROR] 抓取失败：{e}", flush=True)
            continue

        history.append({"role":"user","content":q})
        print("[LLM] 正在生成回答…", flush=True)
        ans = llm.chat(history, max_new_tokens=192, temperature=0.2, top_p=0.9)
        print("\n" + ans + "\n", flush=True)
        history.append({"role":"assistant","content":ans})

if __name__ == '__main__':
    start_session()