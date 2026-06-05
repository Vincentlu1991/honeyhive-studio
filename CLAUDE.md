# CLAUDE.md — HoneyHive Studio 项目主脑

> 面向 AI 编码助手和开发者的项目上下文注入文件。
> 格式参考：Hermes Agent AGENTS.md（NousResearch）+ PRINCE2 / OKR 方法论融合。

---

## 项目定位（一句话）
在 Windows RTX 3070 8GB 本地运行的**生产级多 Agent AI 视频生成平台**，以 ComfyUI 为渲染引擎，以 LangGraph 为编排框架，以 Streamlit 为操作界面。

---

## 核心技术栈
| 组件 | 角色 | 备注 |
|------|------|------|
| ComfyUI | 图像/视频渲染 + 队列 | API: http://127.0.0.1:8188 |
| LangGraph | 多 Agent 编排 | Python，状态机驱动 |
| DSPy | 提示词优化循环 | 可选，需 structured output |
| Ollama | 本地 LLM 运行时 | hermes3:8b（Agent）/ qwen2.5:7b（对话）|
| Streamlit | 操作 GUI | agent-platform/app_robust.py |

---

## 目录结构（关键路径）
```
agent-platform/          # 主应用
	app_robust.py          # 入口 GUI（主文件）
	src/multi_agent_video/ # Agent 包
	config/                # 角色配置、工作流映射
workflow_*.json          # ComfyUI 工作流模板（项目根）
output/skills/           # 可复用技能库（.md）
scripts/                 # 质量门、规划脚本
```

---

## Agent 职责矩阵
| Agent | 输入 | 输出 |
|-------|------|------|
| Supervisor | 用户需求 | 任务图 + 摘要 |
| Story Agent | 需求文本 | scene JSON |
| Prompt Agent | scene JSON | 正/负/运动提示词 |
| Builder Agent | 提示词+参数 | ComfyUI workflow JSON |
| QA Agent | 视频路径 | 评分 JSON + 重试决策 |
| Retriever Agent | 查询词 | 相关文档片段 |
| Report Agent | 执行日志 | Markdown 报告 |

---

## 工程规范（硬约束）
1. **本地优先**：云端调用必须可选，有 fallback
2. **结构化交接**：Agent 间传 JSON/dataclass，禁止裸文本
3. **单一真相源**：每个工作流只有一个 .json，禁止复制修改
4. **质量门**：变更前运行 `scripts/quality-gate.ps1`
5. **小 Agent 原则**：每个 Agent 职责单一，≤ 300 行代码
6. **采样器约束**：sampler_name 只用 `dpmpp_2m`，scheduler 用 `karras`

---

## RTX 3070 8GB 显存约束
- LTXV：最大 768×512，97 帧
- SD1.5 AnimateDiff：最大 512×512，24 帧
- 禁止同时加载两个大模型（OOM）
- 低显存兜底：`workflow_sd15_i2v_medium.json`

---

## 运行手册
1. `ollama serve` 启动本地 LLM
2. 启动 ComfyUI API 服务
3. `cd agent-platform && .\.venv\Scripts\python.exe -m streamlit run app_robust.py`
4. 执行 Supervisor 流程，监控 QA 评分
5. QA 失败 → 自动重试（最多 2 次），仍失败 → 记录 output/run-reports/

---

## 质量验收标准
- 无需手动修改节点即可稳定运行
- QA 失败时重试循环正常触发
- 相同 seed + 工作流 → 可复现输出
- 每次工作流变更更新对应文档

---

## 项目管理（OKR + PRINCE2）

### 当前 OKR
**O：打通完整本地 AI 视频生成闭环**
- KR1：Supervisor → QA 全链路至少 3 次无 OOM 完成
- KR2：技能库 ≥ 5 个 skill，被 Supervisor 正确注入
- KR3：GUI 可切换模型 + 显示 QA 评分历史

### 关键决策日志
| 日期 | 决策 | 原因 |
|------|------|------|
| 2025-Q2 | LTXV 为主力模型 | 运动质量好，VRAM 可控 |
| 2025-Q2 | hermes3:8b 做 Agent / qwen2.5 做对话 | 结构化输出能力差异 |
| 2025-Q3 | CLAUDE.md 注入每个 Supervisor 提示词 | 减少模型上下文遗忘 |

### 风险登记册
| 风险 | 可能性 | 缓解措施 |
|------|--------|---------|
| 显存溢出 OOM | 高 | 分辨率/帧数硬约束，medium 工作流兜底 |
| 模型幻觉导致工作流错误 | 中 | Builder Agent schema 强制验证 |
| ComfyUI API 异常 | 中 | 超时重试最多 3 次，记录日志 |
