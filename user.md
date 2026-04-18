# 项目运行教程

## 快速启动

```bash
# 1. 进入项目目录
cd "/home/ubuntu22/Pigeon nest voice"

# 2. 激活虚拟环境（如果使用）
source .venv/bin/activate

# 3. 启动服务
python3 -m pigeon_nest_voice.main
```

启动成功后终端会显示：
```
✅ 服务就绪: http://0.0.0.0:8000
```

## 访问方式

| 入口 | 地址 | 说明 |
|------|------|------|
| Web 界面 | http://localhost:8000 | 对话 + 语音交互页面 |
| 健康检查 | http://localhost:8000/api/health | 服务状态 |
| 文字对话 API | POST /api/chat | `{"message": "你好", "session_id": ""}` |
| 语音对话 API | POST /api/voice | form-data: audio 文件 + session_id |
| 文字转语音 API | POST /api/tts | `{"text": "你好"}` 返回 MP3 音频流 |

## API 使用示例

### 文字对话

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "session_id": ""}'
```

返回：
```json
{"reply": "你好！有什么可以帮你的？", "session_id": "a1b2c3d4e5f6"}
```

### 语音对话

```bash
curl -X POST http://localhost:8000/api/voice \
  -F "audio=@recording.webm" \
  -F "session_id="
```

返回包含：`reply`（文字回复）、`recognized_text`（识别文字）、`audio_base64`（语音回复 Base64）

### 文字转语音

```bash
curl -X POST http://localhost:8000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "你好世界"}' \
  --output speech.mp3
```

## 任务指令示例

系统支持自然语言任务识别，以下指令会触发规则引擎：

| 说法 | 识别结果 |
|------|---------|
| "帮我拿一袋薯片" | fetch_item → 规则匹配 → 追问位置 |
| "给我水" | fetch_item |
| "打开空调" | control_device |
| "现在几点" | query_time |
| "今天天气怎么样" | query_weather |
| "你好/聊聊天" | 普通对话 → DeepSeek LLM |

## 日志查看

运行时日志输出到终端（彩色）和文件：

```bash
# 实时查看全量日志
tail -f logs/app.log

# 只看错误
tail -f logs/error.log
```

日志级别说明：
- `I` = INFO：正常运行节点（请求、识别结果、LLM 响应）
- `D` = DEBUG：详细调试（意图解析细节、回复内容）
- `W` = WARNING：需要关注（服务降级、模块缺失）
- `E` = ERROR：出错（含完整 traceback）

开启 DEBUG 模式：在 `.env` 中加 `DEBUG=true`

## 停止服务

```bash
# 方式1: 终端 Ctrl+C（优雅关闭）
# 方式2: 强制杀端口
kill $(lsof -t -i:8000)
```

## 注意事项

1. **首次语音请求较慢** — Whisper 模型在第一次语音识别时加载（~1.5GB medium 模型），后续请求复用
2. **会话自动过期** — 会话 30 分钟无活动自动清理，后台每 5 分钟检查一次
3. **HuggingFace 下载慢** — 加环境变量：`HF_ENDPOINT=https://hf-mirror.com python3 -m pigeon_nest_voice.main`
4. **API Key 必填** — `.env` 中的 `DEEPSEEK_API_KEY` 必须配置，否则对话功能无法使用
