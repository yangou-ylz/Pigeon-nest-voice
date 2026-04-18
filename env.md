# 环境配置指南

> 系统: Ubuntu 22.04 LTS | Python 3.10 | 显卡: RTX 5060

## 1. Python 环境

```bash
# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 依赖清单

| 包名 | 用途 |
|------|------|
| fastapi + uvicorn | Web 服务框架 |
| pydantic-settings | 配置管理（读 .env） |
| httpx | 异步 HTTP 客户端（调 DeepSeek API） |
| pyyaml | 规则引擎 YAML 解析 |
| faster-whisper | 本地语音识别（基于 CTranslate2） |
| opencc-python-reimplemented | 繁体→简体转换 |
| edge-tts | 微软 Edge 语音合成（免费） |
| python-multipart | FastAPI 文件上传支持 |

## 2. 环境变量 (.env)

项目根目录创建 `.env` 文件：

```bash
# 必填 — DeepSeek LLM
DEEPSEEK_API_KEY=你的API密钥

# 选填 — 百度 STT（当前未启用，使用本地 Whisper）
BAIDU_STT_APP_ID=
BAIDU_STT_API_KEY=
BAIDU_STT_SECRET_KEY=
```

**获取 DeepSeek API Key**: https://platform.deepseek.com → 注册 → API Keys → 创建

## 3. Whisper 模型（重要）

首次启动时会自动从 HuggingFace 下载 Whisper 模型，当前配置为 `medium`（~1.5GB）。

### 下载慢/失败的解决方案

**方案 A — 使用国内镜像：**
```bash
HF_ENDPOINT=https://hf-mirror.com python3 -m pigeon_nest_voice.main
```

**方案 B — 手动下载：**
```bash
# 模型会缓存到 ~/.cache/huggingface/hub/
# 如果自动下载失败，可以手动用浏览器下载后放到缓存目录
```

### 切换模型大小

编辑 `pigeon_nest_voice/config/settings.py` 中的 `whisper_model` 字段：

| 模型 | 大小 | 速度 | 精度 |
|------|------|------|------|
| tiny | ~75MB | 最快 | 低 |
| base | ~145MB | 快 | 一般 |
| small | ~484MB | 中等 | 较好 |
| **medium** | ~1.5GB | 较慢 | **好（当前）** |
| large | ~3GB | 慢 | 最好 |

也可通过环境变量覆盖：
```bash
WHISPER_MODEL=small python3 -m pigeon_nest_voice.main
```

## 4. 目录结构注意

```
Pigeon nest voice/
├── .env                  # 环境变量（不要提交到 Git）
├── requirements.txt      # Python 依赖
├── rules_config/         # YAML 规则配置文件
├── logs/                 # 运行日志（自动生成，已 gitignore）
│   ├── app.log           # 全量日志（按天轮转，保留 7 天）
│   └── error.log         # 仅 WARNING+（保留 30 天）
└── pigeon_nest_voice/    # 源码
```

## 5. 常见问题

**Q: 提示 `找不到命令 python`**
→ Ubuntu 22.04 默认只有 `python3`，用 `python3` 替代。

**Q: faster-whisper 安装失败**
→ 需要 C++ 编译工具：`sudo apt install build-essential`

**Q: 端口 8000 被占用**
→ `kill $(lsof -t -i:8000)` 杀掉占用进程后重启。

**Q: DeepSeek 返回 402**
→ API 余额不足，去平台充值。
