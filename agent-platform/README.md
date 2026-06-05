# Multi-Agent AI Video Generation Platform (Local-first)

目标：严格控制成本，优先本地模型，提供可视化多 Agent GUI。

## 已实现

- 本地 LLM 优先（默认 Ollama）
- LangGraph 多 Agent 流水线
- 主管 Agent（统筹执行与总结）
- 单 Agent 可分别对话（Story / Prompt / Builder / QA）
- ComfyUI API 渲染 + QA 失败重试

## 1) 安装依赖

```powershell
cd "c:\Users\User\OneDrive\文档\New project\agent-platform"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## 2) 启动本地大模型（Ollama）

如未安装 Ollama，先安装后执行：

```powershell
ollama pull qwen2.5:7b-instruct
ollama run qwen2.5:7b-instruct
```

说明：`qwen2.5:7b-instruct` 对 3070 8GB 比较友好，成本低、响应稳定。

## 3) 配置 `.env`

```env
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_PATH=../workflow_ltxv_img2video_test.json
COMFYUI_TIMEOUT_SECONDS=600
MAX_RENDER_RETRIES=2

ENABLE_LOCAL_LLM=true
LOCAL_LLM_PROVIDER=ollama
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
LOCAL_LLM_MODEL=qwen2.5:7b-instruct
LOCAL_LLM_TIMEOUT_SECONDS=120
```

## 4) 启动前健康检查（推荐）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/health-check.ps1
```

## 4.1) LTX 依赖检查（默认 LTX 工作流推荐先做）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-ltx-dependencies.ps1
```

说明：
- 脚本会检查 ComfyUI 的 `text_encoders` 目录和 `/object_info` 中的 LTX 选项。
- 若依赖不完整，会输出安装步骤并返回退出码 `1`。

## 5) 启动 GUI

```powershell
$env:PYTHONPATH = "src"
streamlit run app_robust.py
```

## 5.1) 构建 LLM Wiki 知识索引（推荐）

```powershell
.\.venv\Scripts\python.exe scripts\build-knowledge-index.py
```

说明：
- 索引来源：`docs/`、`output/skills/`、`CLAUDE.md`
- 配置文件：`config/wiki_knowledge_config.json`
- 输出文件：`output/wiki/knowledge_index.json`
- 状态文件：`output/wiki/knowledge_state.json`

在 GUI 中，侧边栏 `📚 LLM Wiki` 可查看索引状态并一键重建。

覆盖率与质量评测：

```powershell
.\.venv\Scripts\python.exe scripts\wiki-role-coverage-report.py
.\.venv\Scripts\python.exe scripts\wiki-quality-eval.py --min-pass-rate 0.75 --strict
```

Nightly 一键流水线：

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\nightly-knowledge.ps1 -Root .. -MinPassRate 0.75
```

GUI 功能：

- 自动健康检查（Ollama/ComfyUI 连通性）
- 查看所有 Agent
- 点击并分别与每个 Agent 对话
- 通过"主管Agent"统一发起执行
- 执行后看到主管总结 + 全量状态输出
- 完善的错误边界和用户提示

## 6) CLI 运行（可选）

```powershell
$env:PYTHONPATH = "src"
python run_pipeline.py "赛博朋克少女站在雨夜，霓虹灯反射在积水路面"
```

说明：
- 运行结果 JSON 中会包含 `workflow_resolution` 字段。
- 当默认 LTX 缺依赖且启用 fallback 时，可直接看到 `fallback_used` 与 `fallback_reason`。

## 生产级改进（已实现）

- ✅ ComfyUI 客户端：重试机制、指数退避轮询、健康检查
- ✅ Ollama 客户端：重试机制、健康检查、上下文窗口配置
- ✅ 依赖版本：锁定到小版本范围防止破坏性变更
- ✅ GUI 错误边界：完善异常处理和用户友好提示
- ✅ 启动前验证：环境健康检查脚本

## 6) 当前流程

```text
Supervisor Agent
-> Story Agent
-> Prompt Engineer Agent
-> ComfyUI Builder Agent
-> Render (ComfyUI API)
-> QA Agent
-> retry / done
```

## 下一步建议

- 将 prompt/seed 精准注入你 workflow 的具体节点 ID
- 用视频帧分析替代当前 QA 启发式评分
- 接入 DSPy 自动优化 Prompt（离线评测集）

## 知识库架构说明

- 架构文档：`docs/guides/KNOWLEDGE-BASE-ARCHITECTURE.md`
- 文档模板：`docs/templates/Knowledge-Note-Template.md`
