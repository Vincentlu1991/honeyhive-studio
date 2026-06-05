# HoneyHive 员工技能盘点与补强方案（2026-05-30）

## 1. 现有员工与技能总览

### Video Studio 团队
- Supervisor Agent
  - 现有技能: 风险评估、复杂度估计、重试策略、自适应重试预算、run 历史统计。
  - 代码依据: agent-platform/src/multi_agent_video/agents/supervisor_agent.py

- Image Analysis Agent
  - 现有技能: 图像尺寸/方向/亮度/主色分析、构图与视频机会提炼。
  - 代码依据: agent-platform/src/multi_agent_video/agents/image_analysis_agent.py

- Production Planner Agent
  - 现有技能: workflow 类型判定、商业交付风险、成本档位推断。
  - 代码依据: agent-platform/src/multi_agent_video/agents/production_planner_agent.py

- Story Agent
  - 现有技能: 电影镜头语法、动作时长约束、场景与情绪结构化输出。
  - 代码依据: agent-platform/src/multi_agent_video/agents/story_agent.py

- Prompt Agent
  - 现有技能: SD1.5/AnimateDiff 提示词工程、负向词体系、在线参考检索（OpenAlex）。
  - 代码依据: agent-platform/src/multi_agent_video/agents/prompt_agent.py

- Builder Agent
  - 现有技能: ComfyUI 节点映射、prompt/seed 注入、工作流兼容修复建议。
  - 代码依据: agent-platform/src/multi_agent_video/agents/builder_agent.py

- QA Agent
  - 现有技能: 视频质量评分（face/motion/artifact）、问题标签与修复动作。
  - 代码依据: agent-platform/src/multi_agent_video/agents/qa_agent.py

### Personal Secretary 团队
- Supervisor Agent / Retriever Agent / FileOps Agent / Finance Agent / Learning Agent / Business Plan Agent / Report Agent / QA Agent
  - 现有技能: 由 orchestrator 统一编排，覆盖检索、汇总、计划、校验链路。
  - 代码依据: personal-secretary/src/personal_secretary/agent_orchestrator.py

- Document Reader Agent
  - 现有技能: 多格式分块检索、证据引用、冲突检测、敏感信息脱敏、置信度估计。
  - 代码依据: personal-secretary/src/personal_secretary/document_reader_agent.py

- HermesClient
  - 现有技能: hermes/ollama 双后端回退、摘要与问答基础能力。
  - 代码依据: personal-secretary/src/personal_secretary/hermes_client.py

## 2. 技能缺口（按角色）

- 全员通用缺口
  - 缺口1: 长短期记忆统一策略不足（之前主要是无记忆或只保留本次上下文）。
  - 缺口2: 记忆检索评分与遗忘机制未标准化（缺 recency/importance）。
  - 缺口3: 工具调用后“经验沉淀”机制弱（失败模式未自动写回 agent memory）。

- Supervisor 缺口
  - 缺口: 缺少跨团队任务路由评分（技能匹配 + 成本 + 延迟）统一打分器。

- Builder 缺口
  - 缺口: 缺少自动节点发现与 fallback workflow 推荐库（可继续扩大兼容矩阵）。

- QA 缺口
  - 缺口: 缺少基于历史缺陷的“自适应修复处方模板”。

- Secretary 侧缺口
  - 缺口: Document Reader 的证据引用尚未精确到行号/页码坐标级（可提升审计可追溯性）。

## 3. GitHub 参考到的可引入技能

### A. 记忆体系（优先级 P0）
- 来源: microsoft/autogen
  - 证据: python/samples/task_centric_memory/chat_with_teachable_agent.py
  - 证据: python/packages/autogen-agentchat/src/autogen_agentchat/agents/_assistant_agent.py
  - 可引入技能:
    - Teachability-style 记忆注入（用户偏好与经验自动学习）
    - 可插拔 memory backend（内存/文件/向量库）

- 来源: langchain-ai/langgraph
  - 证据: tests 中 StateGraph(MessagesState) + checkpointer=InMemorySaver 模式
  - 可引入技能:
    - thread_id 级别对话持久化
    - agent 分线程记忆隔离

- 来源: langchain-ai/langchain
  - 证据: ConversationSummaryBufferMemory / ConversationEntityMemory
  - 可引入技能:
    - 摘要记忆 + 实体记忆双层结构
    - token 上限触发自动摘要压缩

### B. 提示词与策略优化（优先级 P1）
- 来源: stanfordnlp/dspy
  - 证据: dspy/teleprompt/__init__.py (MIPROv2, BootstrapFewShot 等)
  - 可引入技能:
    - 关键子任务提示词自动优化
    - 小样本任务模板自举（减少人工调 prompt 成本）

### C. 质量闭环（优先级 P1）
- 来源: microsoft/autogen task-centric memory 评测样例
  - 证据: eval_retrieval.py / eval_self_teaching.py
  - 可引入技能:
    - 记忆命中率评估（precision/recall）
    - “失败-修复-学习”自教学循环

## 4. 已落地改动（本次）

- 在 HoneyHive GUI 对话层实现“每员工独立记忆（Hermes 上下文注入）”
  - 持久化文件: output/agent-memory/honeyhive_agent_memory.json
  - 机制:
    - 每个 agent 独立 memory bucket
    - 对话时自动提取近期记忆并注入 prompt
    - 每轮对话后写回记忆并持久化
  - 受益对象:
    - 主管对话（Video 主管 + Secretary 主管）
    - 单Agent对话（所有员工）

## 5. 建议的下一步迭代

- P0: 记忆质量
  - 增加 memory 权重评分: recency + relevance + success_outcome
  - 增加 forget 策略: 超期与低价值自动清理

- P1: 证据级可追溯
  - Document Reader 输出增加 pdf page / csv row / sheet 坐标

- P1: 经理调度智能
  - Supervisor 增加员工路由评分函数（cost, latency, quality）

- P2: 评测
  - 建立 memory 命中率与任务成功率关联报表
