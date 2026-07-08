# 🔍 API Model List & Inspector

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/downloads/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-orange.svg)](#)

Query, test, and audit any OpenAI-compatible API. Detect "bait-and-switch" model fraud.

> 输入自定义 Base URL 和 API Key，查询该 API 下所有可用模型 ID，测试模型能力（视觉 / 工具调用 / JSON），检测"挂羊头卖狗肉"（声称的模型与实际响应不符）。

---

## ✨ Features

- 📋 **list** — 列出 API 下所有可用模型 ID
- 🔬 **test** — 测试单个模型能力：文本对话 / 视觉理解 / 工具调用 / JSON 模式
- 🔍 **check** — 检测"挂羊头卖狗肉"：通过响应 `model` 字段验证模型身份
- 📡 **probe** — 批量探测所有模型（能力探测 or 身份审计）
- 🖥️ **shell** — 交互式 shell 模式：输入一次凭证，反复执行命令
- ⚡ **Zero Dependencies** — 纯 Python 标准库，无需 `pip install`

## 🌐 Supported APIs

Any API implementing the OpenAI `/v1/models` + `/v1/chat/completions` endpoints:

| API | Status | API | Status |
|---|---|---|---|
| OpenAI | ✅ | DeepSeek | ✅ |
| Azure OpenAI | ✅ | Moonshot (Kimi) | ✅ |
| Google Gemini | ✅ | Zhipu (GLM) | ✅ |
| Alibaba (Qwen) | ✅ | Volcengine Ark (Doubao) | ✅ |
| SiliconFlow | ✅ | MiniMax | ✅ |
| Ollama (local) | ✅ | vLLM / LM Studio | ✅ |

---

## 🚀 Quick Start

### Shell 模式（推荐）

输入一次凭证，然后反复操作：

```bash
# 直接进入 shell（启动时询问 URL + Key）
python api_model_list.py shell

# 带凭证进入 shell（跳过询问）
python api_model_list.py shell -u https://api.openai.com/v1 -k sk-xxxx

# 不带子命令也默认进入 shell
python api_model_list.py
```

Shell 内可用命令：

```
list [-f FILTER] [-v] [--json]           列出模型
test  -m MODEL                            测试模型能力 (文本/视觉/工具/JSON)
check -m MODEL                            检测"挂羊头卖狗肉"
probe [-f FILTER] [--identity] [-o FILE]  批量探测
use url <URL>                             切换 API Base URL
use key <KEY>                             切换 API Key
show                                      显示当前配置
help                                      帮助
quit                                      退出
```

Shell 会话示例：

```
============================================================
  🔍 API Model List & Inspector — Shell 模式
============================================================

  📡 Base URL: https://www.sophnet.com/api/open-apis/v1
  🔑 API Key:  sk-xxxx

  ✅ 已连接: https://www.sophnet.com/api/open-apis/v1

  [www.sophnet.com] > list -f GLM
  [www.sophnet.com] > test -m GLM-5.2
  [www.sophnet.com] > check -m GLM-5.2
  [www.sophnet.com] > probe -f Doubao --identity
  [www.sophnet.com] > use key sk-newkey
  [www.sophnet.com] > quit
```

### 单次命令模式

```bash
# 列出所有模型
python api_model_list.py list -u https://api.openai.com/v1 -k sk-xxxx

# 测试单个模型能力
python api_model_list.py test -u https://api.openai.com/v1 -k sk-xxxx -m gpt-4o

# 检测身份欺诈
python api_model_list.py check -u https://api.openai.com/v1 -k sk-xxxx -m gpt-4o

# 批量身份审计
python api_model_list.py probe -u https://api.openai.com/v1 -k sk-xxxx --identity

# 过滤 + 批量审计 + 保存结果
python api_model_list.py probe -u https://api.openai.com/v1 -k sk-xxxx -f gpt --identity -o result.json
```

### Windows

双击 `list_models.bat` 即可进入 shell 模式。

---

## 📖 Subcommands

### `list` — 列出模型

```bash
python api_model_list.py list -u <URL> -k <KEY> [-f FILTER] [-v] [--json] [--full-json]
```

| Option | Description |
|---|---|
| `-f, --filter` | 关键词过滤（不区分大小写） |
| `-v, --verbose` | 显示 Owner + Created 时间 |
| `--json` | 输出 JSON 格式模型 ID 列表 |
| `--full-json` | 输出完整模型信息 JSON |

### `test` — 能力测试

测试单个模型的四项能力：

| 能力 | 测试方法 |
|---|---|
| 文本对话 | 发送简单问候，验证基本响应 |
| 视觉理解 | 发送 1×1 红色 PNG，问"什么颜色" |
| 工具调用 | 提供 `get_weather` 工具定义，问东京天气 |
| JSON 模式 | 使用 `response_format: json_object` 请求 JSON 输出 |

```bash
python api_model_list.py test -u <URL> -k <KEY> -m <MODEL_ID>
```

输出示例：

```
  🔬 模型能力测试: GLM-5.2
  📡 https://api.openai.com/v1/chat/completions

  ⏳ 文本对话... ✅ (1.8s)
     回复: hello world
     响应模型: GLM-5.2
  ⏳ 视觉理解... ❌ (0.2s)
     不支持视觉输入
  ⏳ 工具调用... ✅ (2.0s)
     调用: get_weather({"city": "Tokyo"})
  ⏳ JSON 模式... ✅ (2.5s)
     JSON: {"name": "Alice", "age": 30}

  ──────────────────────────────────────────────────
  📊 能力汇总: GLM-5.2
     ✅ text
     ❌ vision
     ✅ tool_call
     ✅ json_mode
```

### `check` — 身份欺诈检测

检测"挂羊头卖狗肉"——API 中转站声称提供某模型，但实际返回的是另一个模型。

**判定依据（硬证据）：**

| 检测 | 方法 | 可信度 |
|---|---|---|
| 响应 `model` 字段 | API 返回的 `model` 字段是否与请求一致 | 🟢 硬证据，服务端控制 |

**参考信息（不纳入判定）：**

| 检测 | 方法 | 说明 |
|---|---|---|
| 模型自我认知 | 问模型"你是什么模型" | ⚠️ 可被微调/系统提示覆盖，仅供参考 |

> **为什么不用自我认知做判定？** 模型的自我认知可以被微调或系统提示覆盖，模型可以说自己是任何东西。只有 API 响应中的 `model` 字段是服务端控制的硬证据。

```bash
python api_model_list.py check -u <URL> -k <KEY> -m <MODEL_ID>
```

输出示例：

```
  🔍 身份审计: GLM-5.2
  📡 https://api.openai.com/v1/chat/completions

  正在检测... 完成 (2.1s)

  ───────────────────────────────────────────────────────
  🏷️  声称模型:   GLM-5.2
  📋 响应模型:   GLM-5.2
  🗣️  自我认知:   I am GLM (General Language Model)...
      ℹ️  以上仅供参考，不作为判定依据
  ───────────────────────────────────────────────────────
  ✅ 未发现异常

  判定: ✅ 干净 - 响应 model 字段与请求一致
```

判定结果：
- ✅ **干净** — 响应 `model` 字段与请求一致
- 🚫 **欺诈** — 响应 `model` 字段与请求不符

### `probe` — 批量探测

```bash
# 能力探测（默认）
python api_model_list.py probe -u <URL> -k <KEY> [-f FILTER] [-o OUTPUT]

# 身份审计
python api_model_list.py probe -u <URL> -k <KEY> [--identity] [-o OUTPUT]
```

能力探测输出示例：

```
  🔬 模式: 能力探测 (capability probe)
     #  Model ID                    Text   Vision   Tool   JSON
  ──────────────────────────────────────────────────────────────
     1  Doubao-Seed-1.6-vision      ✅     ❌       ✅     ✅
     2  Doubao-Seed-1.6             ✅     ❌       ✅     ❌
     3  Doubao-Seed-1.6-flash       ✅     ❌       ✅     ✅
  ──────────────────────────────────────────────────────────────
  汇总: 文本 3/3 | 视觉 0/3 | 工具 3/3 | JSON 2/3
```

身份审计输出示例：

```
  🔍 模式: 身份审计 (identity check)
     #  Model ID                    Response Model             Verdict
  ──────────────────────────────────────────────────────────────────────
     1  Doubao-Seed-1.6-vision      Doubao-Seed-1.6-vision     ✅
     2  Doubao-Seed-1.6             Doubao-Seed-1.6            ✅
     3  Doubao-Seed-1.6-flash       Doubao-Seed-1.6-flash      ✅
  ──────────────────────────────────────────────────────────────────────
  汇总: ✅ 3 干净 | 🚫 0 欺诈 | ❌ 0 错误
```

---

## 🔗 URL Handling

智能处理各种 URL 格式，自动拼接 `/models` 和 `/chat/completions` 端点：

| Input | Resolved URL |
|---|---|
| `https://api.openai.com` | `https://api.openai.com/v1/models` |
| `https://api.openai.com/v1` | `https://api.openai.com/v1/models` |
| `https://api.openai.com/v1/models` | `https://api.openai.com/v1/models`（直通） |
| `http://localhost:11434` | `http://localhost:11434/v1/models` |
| `https://api.openai.com/v1?foo=bar` | `https://api.openai.com/v1/models?foo=bar` |

---

## 📁 Project Structure

```
api-model-list/
├── api_model_list.py    # 主程序 (纯 Python 标准库，零依赖)
├── list_models.bat      # Windows 启动器 (双击进入 shell)
├── pyproject.toml       # 打包配置
├── README.md            # 本文件
├── LICENSE              # AGPL v3
└── .gitignore
```

---

## 📄 License

**API Model List & Inspector** — Copyright 2024 Raya Friandion

Licensed under the **GNU Affero General Public License v3 or later** (AGPL-3.0-or-later).

See [LICENSE](LICENSE) for the full text.

> AGPL v3 要求：如果你通过网络提供服务，且使用了本项目的代码，你必须向用户提供你修改后的完整源代码。
