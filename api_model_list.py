#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2024 Raya Friandion
#
# API Model List & Inspector - 查询 / 测试 / 审计 OpenAI 兼容 API
# =================================================================
# 子命令:
#   list   - 列出 API 下所有可用模型 ID
#   test   - 对单个模型做能力测试 (文本 / 视觉 / 工具调用 / JSON)
#   check  - 检测"挂羊头卖狗肉" (声称的模型 vs 实际响应的模型)
#   probe  - 批量探测所有模型的能力和身份
#   shell  - 交互式 shell 模式 (输入一次凭证后反复操作)
#
# 兼容所有 OpenAI API 格式的服务：
#   OpenAI / Azure / Anthropic / Google Gemini / 通义千问 / 智谱 /
#   Moonshot / DeepSeek / SiliconFlow / Volcengine Ark / 本地 Ollama / vLLM 等
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ── 常量 ────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 60
USER_AGENT = "api-model-list/2.0"

# 标准测试用图片 (1x1 红色像素 PNG, base64)
TINY_RED_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)

# ── URL 工具 ────────────────────────────────────────────────────────


def build_models_url(base_url: str) -> str:
    """根据 Base URL 构造 /models 端点。"""
    url = base_url.strip().rstrip("/")
    if url.endswith("/models"):
        return url
    path_part = url.split("://", 1)[-1]
    query_suffix = ""
    for sep in ("?", "#"):
        idx = path_part.find(sep)
        if idx >= 0:
            query_suffix = path_part[idx:]
            path_part = path_part[:idx]
            break
    segments = [s for s in path_part.split("/") if s]
    base = url[: len(url) - len(query_suffix)] if query_suffix else url
    if segments and segments[-1] in ("v1", "v2"):
        return base + "/models" + query_suffix
    return base + "/v1/models" + query_suffix


def build_chat_url(base_url: str) -> str:
    """根据 Base URL 构造 /chat/completions 端点。"""
    url = build_models_url(base_url)
    return url[: url.rfind("/models")] + "/chat/completions"


# ── HTTP 核心 ───────────────────────────────────────────────────────


def _make_request(url: str, api_key: str, payload: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """发送 POST 请求到 chat/completions，返回解析后的 JSON。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key and api_key.strip():
        key = api_key.strip()
        headers["Authorization"] = key if key.lower().startswith("bearer ") else f"Bearer {key}"

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")

    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def _make_get(url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """发送 GET 请求，返回解析后的 JSON。"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    if api_key and api_key.strip():
        key = api_key.strip()
        headers["Authorization"] = key if key.lower().startswith("bearer ") else f"Bearer {key}"

    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def query_models(base_url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """查询 /models 端点。"""
    return _make_get(build_models_url(base_url), api_key, timeout)


def extract_models(response: dict) -> list[dict]:
    """从 API 响应中提取模型列表。"""
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        if "data" in response and isinstance(response["data"], list):
            return response["data"]
        if "models" in response and isinstance(response["models"], list):
            return response["models"]
    return []


def filter_models(models: list[dict], keyword: str = "") -> list[dict]:
    if not keyword:
        return models
    kw = keyword.lower()
    return [m for m in models if kw in str(m.get("id", "")).lower()]


def format_timestamp(ts) -> str:
    if not ts:
        return ""
    try:
        ts_int = int(ts)
        if ts_int > 1e12:
            ts_int = ts_int // 1000
        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, OSError):
        return str(ts)


# ── 能力测试 ────────────────────────────────────────────────────────


def test_text(model: str, url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """测试基本文本对话能力。"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say exactly: hello world"}],
        "max_tokens": 50,
        "temperature": 0,
    }
    try:
        resp = _make_request(url, api_key, payload, timeout)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "content": content.strip(), "raw_model": resp.get("model", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_vision(model: str, url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """测试视觉能力 - 发送一张红色图片让模型描述颜色。"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{TINY_RED_PNG_B64}"},
                    },
                    {"type": "text", "text": "What color is this image? Answer in one word."},
                ],
            }
        ],
        "max_tokens": 20,
        "temperature": 0,
    }
    try:
        resp = _make_request(url, api_key, payload, timeout)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"ok": True, "content": content.strip(), "raw_model": resp.get("model", "")}
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}", "detail": body[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_tool_call(model: str, url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """测试工具调用能力。"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "What is the weather in Tokyo? Use the get_weather tool."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "City name"},
                        },
                        "required": ["city"],
                    },
                },
            }
        ],
        "max_tokens": 100,
        "temperature": 0,
    }
    try:
        resp = _make_request(url, api_key, payload, timeout)
        msg = resp.get("choices", [{}])[0].get("message", {})
        tool_calls = msg.get("tool_calls", [])
        return {
            "ok": True,
            "has_tool_calls": len(tool_calls) > 0,
            "tool_calls": tool_calls,
            "raw_model": resp.get("model", ""),
        }
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}", "detail": body[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_json_mode(model: str, url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """测试 JSON 模式输出。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a JSON generator. Always output valid JSON."},
            {"role": "user", "content": "Return a JSON object with keys 'name' and 'age' for a person named Alice aged 30."},
        ],
        "max_tokens": 100,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = _make_request(url, api_key, payload, timeout)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        is_valid_json = False
        parsed = None
        try:
            parsed = json.loads(content)
            is_valid_json = True
        except (json.JSONDecodeError, TypeError):
            pass
        return {
            "ok": True,
            "content": content.strip(),
            "is_valid_json": is_valid_json,
            "parsed": parsed,
            "raw_model": resp.get("model", ""),
        }
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}", "detail": body[:300]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 身份检测 ────────────────────────────────────────────────────────


def check_identity(model: str, url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """检测"挂羊头卖狗肉" - 声称的模型 vs 实际响应。

    判定依据 (硬证据):
      响应中的 model 字段 - API 返回的模型标识，由服务端控制，模型无法伪造

    参考信息 (不纳入判定):
      自我认知 - 直接问模型 "What is your model name?"
      模型的自我认知可以被微调/系统提示覆盖，不可作为判据，仅供参考
    """
    result = {
        "claimed_model": model,
        "response_model": "",
        "self_identified_as": "",
        "suspicions": [],
        "verdict": "unknown",
    }

    # ── 1. 响应 model 字段 (硬证据) ──
    text_result = test_text(model, url, api_key, timeout)
    if text_result["ok"]:
        resp_model = text_result.get("raw_model", "")
        result["response_model"] = resp_model
        if resp_model and resp_model != model:
            result["suspicions"].append(
                f"响应 model 字段 '{resp_model}' ≠ 请求 '{model}'"
            )
    else:
        result["suspicions"].append(f"文本测试失败: {text_result.get('error', '')}")
        result["verdict"] = "error"
        return result

    # ── 2. 自我认知 (仅供参考，不纳入判定) ──
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "What is your exact model name and version? If you are not sure, say what model you think you are. Answer briefly.",
            }
        ],
        "max_tokens": 100,
        "temperature": 0,
    }
    try:
        resp = _make_request(url, api_key, payload, timeout)
        self_id = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        result["self_identified_as"] = self_id
    except Exception as e:
        result["self_identified_as"] = f"(查询失败: {e})"

    # ── 判定 (仅基于硬证据) ──
    if len(result["suspicions"]) == 0:
        result["verdict"] = "clean"
    else:
        result["verdict"] = "fraud"

    return result


# ── 子命令实现 ──────────────────────────────────────────────────────


def cmd_list(args):
    """list 子命令 - 列出模型。"""
    models_url = build_models_url(args.url)
    print()
    try:
        resp = query_models(args.url, args.key, timeout=args.timeout)
    except Exception as e:
        handle_error(e, args.url)
        sys.exit(1)

    model_list = extract_models(resp)
    if not model_list:
        print("  ⚠️ API 返回了响应，但没有找到模型数据", file=sys.stderr)
        print(f"  📡 请求 URL: {models_url}", file=sys.stderr)
        sys.exit(1)

    if args.filter:
        total = len(model_list)
        model_list = filter_models(model_list, args.filter)
        print(f"  ✅ 查询成功！\n")
        print(f"  📡 {models_url}")
        print(f"  🔍 过滤: '{args.filter}'  |  {len(model_list)}/{total} 个模型\n")
    else:
        print(f"  ✅ 查询成功！\n")
        print(f"  📡 {models_url}")
        print(f"  📦 共 {len(model_list)} 个模型\n")

    if args.json:
        ids = sorted(str(m.get("id", "")) for m in model_list)
        json.dump(ids, sys.stdout, indent=2, ensure_ascii=False)
        print()
    elif args.full_json:
        sorted_list = sorted(model_list, key=lambda m: str(m.get("id", "")))
        json.dump(sorted_list, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print_models_table(model_list, verbose=args.verbose)


def cmd_test(args):
    """test 子命令 - 测试单个模型能力。"""
    chat_url = build_chat_url(args.url)
    print(f"\n  🔬 模型能力测试: {args.model}")
    print(f"  📡 {chat_url}\n")

    capabilities = []

    # 文本
    print("  ⏳ 文本对话...", end="", flush=True)
    t0 = time.time()
    r = test_text(args.model, chat_url, args.key, args.timeout)
    dt = time.time() - t0
    if r["ok"]:
        print(f" ✅ ({dt:.1f}s)")
        print(f"     回复: {r['content'][:80]}")
        if r.get("raw_model"):
            print(f"     响应模型: {r['raw_model']}")
        capabilities.append(("text", True))
    else:
        print(f" ❌ ({dt:.1f}s)")
        print(f"     错误: {r.get('error', '')}")
        if r.get("detail"):
            print(f"     详情: {r['detail'][:120]}")
        capabilities.append(("text", False))

    # 视觉
    print("  ⏳ 视觉理解...", end="", flush=True)
    t0 = time.time()
    r = test_vision(args.model, chat_url, args.key, args.timeout)
    dt = time.time() - t0
    if r["ok"]:
        print(f" ✅ ({dt:.1f}s)")
        print(f"     回复: {r['content'][:80]}")
        capabilities.append(("vision", True))
    else:
        print(f" ❌ ({dt:.1f}s)")
        err = r.get("error", "")
        if "400" in err or "image" in r.get("detail", "").lower():
            print(f"     不支持视觉输入")
        else:
            print(f"     错误: {err}")
            if r.get("detail"):
                print(f"     详情: {r['detail'][:120]}")
        capabilities.append(("vision", False))

    # 工具调用
    print("  ⏳ 工具调用...", end="", flush=True)
    t0 = time.time()
    r = test_tool_call(args.model, chat_url, args.key, args.timeout)
    dt = time.time() - t0
    if r["ok"]:
        has_tc = r.get("has_tool_calls", False)
        if has_tc:
            print(f" ✅ ({dt:.1f}s)")
            tc = r.get("tool_calls", [{}])[0]
            fn_name = tc.get("function", {}).get("name", "?")
            fn_args = tc.get("function", {}).get("arguments", "")
            print(f"     调用: {fn_name}({fn_args[:60]})")
        else:
            print(f" ⚠️ ({dt:.1f}s) 未调用工具 (模型直接回答了)")
        capabilities.append(("tool_call", has_tc))
    else:
        print(f" ❌ ({dt:.1f}s)")
        err = r.get("error", "")
        if "400" in err or "tool" in r.get("detail", "").lower():
            print(f"     不支持工具调用")
        else:
            print(f"     错误: {err}")
        capabilities.append(("tool_call", False))

    # JSON 模式
    print("  ⏳ JSON 模式...", end="", flush=True)
    t0 = time.time()
    r = test_json_mode(args.model, chat_url, args.key, args.timeout)
    dt = time.time() - t0
    if r["ok"]:
        valid = r.get("is_valid_json", False)
        if valid:
            print(f" ✅ ({dt:.1f}s)")
            print(f"     JSON: {json.dumps(r.get('parsed', {}), ensure_ascii=False)[:80]}")
        else:
            print(f" ⚠️ ({dt:.1f}s) 返回了内容但不是有效 JSON")
            print(f"     回复: {r.get('content', '')[:80]}")
        capabilities.append(("json_mode", valid))
    else:
        print(f" ❌ ({dt:.1f}s)")
        err = r.get("error", "")
        if "400" in err or "response_format" in r.get("detail", "").lower():
            print(f"     不支持 JSON 模式")
        else:
            print(f"     错误: {err}")
        capabilities.append(("json_mode", False))

    # 汇总
    print(f"\n  {'─' * 50}")
    print(f"  📊 能力汇总: {args.model}")
    for cap, ok in capabilities:
        status = "✅" if ok else "❌"
        print(f"     {status} {cap}")
    print()


def cmd_check(args):
    """check 子命令 - 身份欺诈检测。"""
    chat_url = build_chat_url(args.url)
    print(f"\n  🔍 身份审计: {args.model}")
    print(f"  📡 {chat_url}\n")

    print("  正在检测...", end="", flush=True)
    t0 = time.time()
    result = check_identity(args.model, chat_url, args.key, args.timeout)
    dt = time.time() - t0
    print(f" 完成 ({dt:.1f}s)\n")

    print(f"  {'─' * 55}")
    print(f"  🏷️  声称模型:   {result['claimed_model']}")
    print(f"  📋 响应模型:   {result['response_model'] or '(未返回)'}")
    print(f"  🗣️  自我认知:   {result['self_identified_as'][:80] or '(无回答)'}")
    print(f"      ℹ️  以上仅供参考，不作为判定依据")
    print(f"  {'─' * 55}")

    if result["suspicions"]:
        print(f"  🚫 发现 {len(result['suspicions'])} 个铁证:")
        for i, s in enumerate(result["suspicions"], 1):
            print(f"     {i}. {s}")
    else:
        print(f"  ✅ 未发现异常")

    verdict_map = {
        "clean": ("✅ 干净", "响应 model 字段与请求一致"),
        "fraud": ("🚫 欺诈", "响应 model 字段与请求不符！"),
        "error": ("❌ 错误", "检测过程中发生错误"),
        "unknown": ("❓ 未知", "无法判定"),
    }
    emoji_label, desc = verdict_map.get(result["verdict"], ("❓", ""))
    print(f"\n  判定: {emoji_label} - {desc}")
    print()


def cmd_probe(args):
    """probe 子命令 - 批量探测所有模型。"""
    models_url = build_models_url(args.url)
    chat_url = build_chat_url(args.url)

    # 获取模型列表
    print(f"\n  📡 获取模型列表...", end="", flush=True)
    try:
        resp = query_models(args.url, args.key, timeout=args.timeout)
    except Exception as e:
        print(f" ❌")
        handle_error(e, args.url)
        sys.exit(1)
    model_list = extract_models(resp)
    if not model_list:
        print(f" ❌ 没有找到模型")
        sys.exit(1)
    print(f" ✅ {len(model_list)} 个模型\n")

    if args.filter:
        model_list = filter_models(model_list, args.filter)
        print(f"  🔍 过滤后: {len(model_list)} 个模型\n")

    # 选择探测模式
    if args.identity:
        print(f"  🔍 模式: 身份审计 (identity check)")
        _probe_identity_batch(model_list, chat_url, args)
    else:
        print(f"  🔬 模式: 能力探测 (capability probe)")
        _probe_capability_batch(model_list, chat_url, args)


def _probe_capability_batch(models: list[dict], chat_url: str, args):
    """批量能力探测。"""
    results = []
    total = len(models)
    print(f"  {'#':>4}  {'Model ID':<40} {'Text':<6} {'Vision':<8} {'Tool':<6} {'JSON':<6}")
    print(f"  {'─' * 75}")

    for i, m in enumerate(models, 1):
        mid = str(m.get("id", "?"))
        print(f"  {i:>4}  {mid:<40}", end="", flush=True)

        row = {"id": mid, "text": False, "vision": False, "tool": False, "json": False}

        # 文本
        r = test_text(mid, chat_url, args.key, args.timeout)
        row["text"] = r["ok"]
        row["response_model"] = r.get("raw_model", "")
        print(f" {'✅' if r['ok'] else '❌':<5}", end="")

        # 视觉
        r = test_vision(mid, chat_url, args.key, args.timeout)
        row["vision"] = r["ok"]
        print(f" {'✅' if r['ok'] else '❌':<7}", end="")

        # 工具
        r = test_tool_call(mid, chat_url, args.key, args.timeout)
        row["tool"] = r.get("has_tool_calls", False)
        print(f" {'✅' if row['tool'] else '❌':<5}", end="")

        # JSON
        r = test_json_mode(mid, chat_url, args.key, args.timeout)
        row["json"] = r.get("is_valid_json", False)
        print(f" {'✅' if row['json'] else '❌':<5}")

        results.append(row)

    # 汇总
    print(f"  {'─' * 75}")
    t = sum(1 for r in results if r["text"])
    v = sum(1 for r in results if r["vision"])
    tc = sum(1 for r in results if r["tool"])
    js = sum(1 for r in results if r["json"])
    print(f"  汇总: 文本 {t}/{total} | 视觉 {v}/{total} | 工具 {tc}/{total} | JSON {js}/{total}")
    print()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"  💾 已保存到: {args.output}\n")


def _probe_identity_batch(models: list[dict], chat_url: str, args):
    """批量身份审计。"""
    results = []
    total = len(models)
    print(f"  {'#':>4}  {'Model ID':<40} {'Response Model':<35} {'Verdict'}")
    print(f"  {'─' * 90}")

    for i, m in enumerate(models, 1):
        mid = str(m.get("id", "?"))
        print(f"  {i:>4}  {mid:<40}", end="", flush=True)

        result = check_identity(mid, chat_url, args.key, args.timeout)
        results.append(result)

        resp_model = result["response_model"] or "(空)"
        verdict_emoji = {"clean": "✅", "fraud": "🚫", "error": "❌", "unknown": "❓"}
        v = verdict_emoji.get(result["verdict"], "❓")
        print(f" {resp_model:<35} {v}")

    print(f"  {'─' * 90}")
    clean = sum(1 for r in results if r["verdict"] == "clean")
    fraud = sum(1 for r in results if r["verdict"] == "fraud")
    err = sum(1 for r in results if r["verdict"] == "error")
    print(f"  汇总: ✅ {clean} 干净 | 🚫 {fraud} 欺诈 | ❌ {err} 错误")
    print()

    # 输出欺诈详情
    flagged = [r for r in results if r["verdict"] == "fraud"]
    if flagged:
        print(f"  🚫 发现欺诈的模型:")
        for r in flagged:
            print(f"     {r['claimed_model']}:")
            for s in r["suspicions"]:
                print(f"       - {s}")
        print()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"  💾 已保存到: {args.output}\n")


# ── 输出工具 ────────────────────────────────────────────────────────


def print_models_table(models: list[dict], verbose: bool = False, file=None):
    if file is None:
        file = sys.stdout
    if not models:
        print("  (没有找到模型)", file=file)
        return
    sorted_models = sorted(models, key=lambda m: str(m.get("id", "")))
    if verbose:
        print(f"{'#':>4}  {'Model ID':<55} {'Owner':<20} {'Created'}", file=file)
        print("-" * 100, file=file)
        for i, m in enumerate(sorted_models, 1):
            mid = str(m.get("id", "?"))[:55]
            owner = str(m.get("owned_by", m.get("owner", "")))[:20]
            created = format_timestamp(m.get("created", ""))
            print(f"{i:>4}  {mid:<55} {owner:<20} {created}", file=file)
        print("-" * 100, file=file)
        print(f"  共 {len(sorted_models)} 个模型", file=file)
    else:
        print(f"{'#':>4}  {'Model ID'}", file=file)
        print("-" * 65, file=file)
        for i, m in enumerate(sorted_models, 1):
            print(f"{i:>4}  {m.get('id', '?')}", file=file)
        print("-" * 65, file=file)
        print(f"  共 {len(sorted_models)} 个模型", file=file)


def handle_error(e: Exception, base_url: str):
    print(f"\n  ❌ 查询失败！", file=sys.stderr)
    if isinstance(e, HTTPError):
        code = e.code
        reason = e.reason
        err_detail = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(body)
                err_msg = (
                    err_json.get("error", {}).get("message", "")
                    if isinstance(err_json.get("error"), dict)
                    else err_json.get("message", "")
                )
                if err_msg:
                    err_detail = f"\n  📋 详情: {err_msg}"
            except (json.JSONDecodeError, AttributeError):
                if body and len(body) < 500:
                    err_detail = f"\n  📋 详情: {body}"
        except Exception:
            pass
        error_map = {
            401: "🔑 认证失败 - API Key 无效或缺失",
            403: "🚫 访问被拒绝 - 权限不足或 IP 被限制",
            404: "🔍 端点不存在 - 请检查 URL 是否正确",
            429: "⏰ 请求频率超限 - 请稍后再试",
            500: "💥 服务器内部错误",
            502: "💥 网关错误",
            503: "💤 服务暂时不可用",
            504: "💤 网关超时",
        }
        hint = error_map.get(code, f"HTTP {code}")
        print(f"  {hint}", file=sys.stderr)
        print(f"  📡 状态码: {code} {reason}", file=sys.stderr)
        if err_detail:
            print(err_detail, file=sys.stderr)
    elif isinstance(e, URLError):
        reason = str(e.reason)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            print(f"  ⏰ 连接超时", file=sys.stderr)
        elif "getaddrinfo" in reason.lower():
            print(f"  🌐 无法解析主机名", file=sys.stderr)
        elif "connection refused" in reason.lower():
            print(f"  🚫 连接被拒绝", file=sys.stderr)
        elif "ssl" in reason.lower():
            print(f"  🔒 SSL/TLS 证书错误", file=sys.stderr)
        else:
            print(f"  🌐 网络错误: {reason}", file=sys.stderr)
    elif isinstance(e, json.JSONDecodeError):
        print(f"  📄 响应不是有效的 JSON", file=sys.stderr)
    elif isinstance(e, ValueError):
        print(f"  ⚠️ {e}", file=sys.stderr)
    else:
        print(f"  🐛 {type(e).__name__}: {e}", file=sys.stderr)
    print(f"\n  📡 请求 URL: {build_models_url(base_url)}", file=sys.stderr)


# ── 交互模式 ────────────────────────────────────────────────────────


def interactive_prompt() -> tuple[str, str]:
    """交互式输入 Base URL 和 API Key。"""
    print("=" * 60)
    print("  🔍 API Model List & Inspector")
    print("=" * 60)
    print()
    base_url = input("  📡 Base URL (如 https://api.openai.com/v1): ").strip()
    if not base_url:
        print("\n  ❌ Base URL 不能为空！")
        sys.exit(1)
    api_key = input("  🔑 API Key (可直接粘贴，或按回车跳过): ").strip()
    return base_url, api_key


# ── Shell 模式 ──────────────────────────────────────────────────────

SHELL_HELP = """\
  可用命令:
    list [-f FILTER] [-v] [--json]       列出模型
    test  -m MODEL                        测试模型能力 (文本/视觉/工具/JSON)
    check -m MODEL                        检测"挂羊头卖狗肉"
    probe [-f FILTER] [--identity] [-o FILE]  批量探测
    models                                重新列出模型 (同 list)
    use url <URL>                         切换 API Base URL
    use key <KEY>                         切换 API Key
    use url <URL> key <KEY>               同时切换
    show                                  显示当前配置
    help                                  显示此帮助
    quit / exit                           退出
"""


def shell_mode(initial_url: str = "", initial_key: str = ""):
    """交互式 shell：输入一次凭证，反复执行子命令。"""
    base_url = initial_url
    api_key = initial_key

    # 如果没有通过参数传入，先问一次
    if not base_url:
        print("=" * 60)
        print("  🔍 API Model List & Inspector — Shell 模式")
        print("=" * 60)
        print()
        try:
            base_url = input("  📡 Base URL (如 https://api.openai.com/v1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  👋 再见~")
            return
        if not base_url:
            print("\n  ❌ Base URL 不能为空！")
            return
        try:
            api_key = input("  🔑 API Key (可直接粘贴，或按回车跳过): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  👋 再见~")
            return

    print(f"\n  ✅ 已连接: {base_url}")
    print(f"  输入 help 查看命令，quit 退出\n")

    # 缓存的模型列表
    cached_models: list[str] = []

    while True:
        try:
            raw = input(f"  [{base_url.split('://')[-1].split('/')[0]}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  👋 再见~")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        rest = parts[1:]

        try:
            if cmd in ("quit", "exit", "q"):
                print("  👋 再见~")
                break

            elif cmd == "help":
                print(SHELL_HELP)

            elif cmd == "show":
                print(f"  📡 URL: {base_url}")
                masked = api_key[:8] + "..." if api_key else "(空)"
                print(f"  🔑 Key: {masked}")

            elif cmd == "use":
                # use url <URL>  /  use key <KEY>  /  use url <URL> key <KEY>
                i = 0
                while i < len(rest):
                    if rest[i].lower() == "url" and i + 1 < len(rest):
                        base_url = rest[i + 1]
                        i += 2
                    elif rest[i].lower() == "key" and i + 1 < len(rest):
                        api_key = rest[i + 1]
                        i += 2
                    else:
                        i += 1
                cached_models.clear()
                print(f"  ✅ 已更新: {base_url}")

            elif cmd == "list" or cmd == "models":
                args = argparse.Namespace(
                    url=base_url, key=api_key, filter="",
                    verbose=False, json=False, full_json=False,
                    timeout=DEFAULT_TIMEOUT,
                )
                # 解析 list 后面的参数
                j = 0
                while j < len(rest):
                    if rest[j] in ("-f", "--filter") and j + 1 < len(rest):
                        args.filter = rest[j + 1]; j += 2
                    elif rest[j] in ("-v", "--verbose"):
                        args.verbose = True; j += 1
                    elif rest[j] == "--json":
                        args.json = True; j += 1
                    elif rest[j] == "--full-json":
                        args.full_json = True; j += 1
                    else:
                        j += 1
                cmd_list(args)

            elif cmd == "test":
                model = ""
                j = 0
                while j < len(rest):
                    if rest[j] in ("-m", "--model") and j + 1 < len(rest):
                        model = rest[j + 1]; j += 2
                    else:
                        j += 1
                if not model:
                    print("  ❌ 用法: test -m <MODEL_ID>")
                    continue
                args = argparse.Namespace(
                    url=base_url, key=api_key, model=model,
                    timeout=DEFAULT_TIMEOUT,
                )
                cmd_test(args)

            elif cmd == "check":
                model = ""
                j = 0
                while j < len(rest):
                    if rest[j] in ("-m", "--model") and j + 1 < len(rest):
                        model = rest[j + 1]; j += 2
                    else:
                        j += 1
                if not model:
                    print("  ❌ 用法: check -m <MODEL_ID>")
                    continue
                args = argparse.Namespace(
                    url=base_url, key=api_key, model=model,
                    timeout=DEFAULT_TIMEOUT,
                )
                cmd_check(args)

            elif cmd == "probe":
                args = argparse.Namespace(
                    url=base_url, key=api_key, filter="",
                    identity=False, output=None,
                    timeout=DEFAULT_TIMEOUT,
                )
                j = 0
                while j < len(rest):
                    if rest[j] in ("-f", "--filter") and j + 1 < len(rest):
                        args.filter = rest[j + 1]; j += 2
                    elif rest[j] == "--identity":
                        args.identity = True; j += 1
                    elif rest[j] in ("-o", "--output") and j + 1 < len(rest):
                        args.output = rest[j + 1]; j += 2
                    else:
                        j += 1
                cmd_probe(args)

            else:
                print(f"  ❌ 未知命令: {cmd}  (输入 help 查看可用命令)")

        except KeyboardInterrupt:
            print("\n  ⏹️  已中断")
        except Exception as e:
            print(f"\n  ❌ 错误: {e}")


# ── 主入口 ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="查询 / 测试 / 审计 OpenAI 兼容 API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  # Shell 模式 (推荐，输入一次凭证后反复操作)
  python api_model_list.py shell
  python api_model_list.py shell -u https://api.openai.com/v1 -k sk-xxxx

  # 单次命令模式
  python api_model_list.py list -u https://api.openai.com/v1 -k sk-xxxx
  python api_model_list.py test -u https://api.openai.com/v1 -k sk-xxxx -m gpt-4o
  python api_model_list.py check -u https://api.openai.com/v1 -k sk-xxxx -m gpt-4o
  python api_model_list.py probe -u https://api.openai.com/v1 -k sk-xxxx --identity

  # 不带子命令也进入 shell
  python api_model_list.py
""",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── shell ──
    p_shell = sub.add_parser("shell", help="交互式 shell 模式 (输入一次凭证后反复操作)")
    p_shell.add_argument("-u", "--url", default="", help="API Base URL (不传则启动时询问)")
    p_shell.add_argument("-k", "--key", default="", help="API Key")
    p_shell.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时秒数 (默认 {DEFAULT_TIMEOUT})")

    # ── list ──
    p_list = sub.add_parser("list", help="列出 API 下所有可用模型 ID")
    p_list.add_argument("-u", "--url", help="API Base URL")
    p_list.add_argument("-k", "--key", help="API Key")
    p_list.add_argument("-f", "--filter", default="", help="过滤模型")
    p_list.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")
    p_list.add_argument("--json", action="store_true", help="输出 JSON 格式模型 ID 列表")
    p_list.add_argument("--full-json", action="store_true", help="输出完整 JSON")
    p_list.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时秒数 (默认 {DEFAULT_TIMEOUT})")

    # ── test ──
    p_test = sub.add_parser("test", help="测试单个模型能力 (文本/视觉/工具/JSON)")
    p_test.add_argument("-u", "--url", required=True, help="API Base URL")
    p_test.add_argument("-k", "--key", help="API Key")
    p_test.add_argument("-m", "--model", required=True, help="模型 ID")
    p_test.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时秒数 (默认 {DEFAULT_TIMEOUT})")

    # ── check ──
    p_check = sub.add_parser("check", help='检测"挂羊头卖狗肉" - 模型身份欺诈检测')
    p_check.add_argument("-u", "--url", required=True, help="API Base URL")
    p_check.add_argument("-k", "--key", help="API Key")
    p_check.add_argument("-m", "--model", required=True, help="模型 ID")
    p_check.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时秒数 (默认 {DEFAULT_TIMEOUT})")

    # ── probe ──
    p_probe = sub.add_parser("probe", help="批量探测所有模型")
    p_probe.add_argument("-u", "--url", required=True, help="API Base URL")
    p_probe.add_argument("-k", "--key", help="API Key")
    p_probe.add_argument("-f", "--filter", default="", help="过滤模型")
    p_probe.add_argument("--identity", action="store_true", help="身份审计模式 (默认为能力探测)")
    p_probe.add_argument("-o", "--output", help="保存结果到 JSON 文件")
    p_probe.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"超时秒数 (默认 {DEFAULT_TIMEOUT})")

    args = parser.parse_args()

    # 没有子命令 -> 进入 shell
    if not args.command:
        shell_mode()
        return

    # shell 子命令
    if args.command == "shell":
        shell_mode(initial_url=args.url, initial_key=args.key)
        return

    # list 子命令的交互模式
    if args.command == "list" and not args.url:
        base_url, api_key = interactive_prompt()
        args.url = base_url
        args.key = api_key

    # 执行
    if args.command == "list":
        cmd_list(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "probe":
        cmd_probe(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
