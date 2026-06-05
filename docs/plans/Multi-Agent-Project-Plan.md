# Multi-Agent AI Video Generation Platform 实战路线（3070 8GB）

## 总原则

- 不做单一超大 Agent，采用多 Agent 专职分工
- 先确保可运行闭环，再追求质量
- 本地模型优先，云端仅用于可替代环节

## 1个月（Prompt Skill + API闭环）

目标：把 Prompt 变成可优化程序。

- 学习重点
  - DSPy 基础编程模式
  - Pydantic 结构化输出
  - ComfyUI API 提交/轮询
- 交付物
  - Prompt Engineer Agent
  - 可回放的小型评测集（20条 brief）
  - Prompt v1->v2 自动对比脚本

## 2个月（多 Agent 编排）

目标：把单次生成升级为可重试的流水线。

- 学习重点
  - LangGraph 状态图与条件分支
  - CrewAI 或 LangGraph 子图协作
  - 失败回路与重试策略
- 交付物
  - Story/Prompt/Builder/QA/Render 五 Agent
  - 自动重试与日志追踪
  - 质量阈值控制（face/motion/artifact）

## 3个月（抖音发布工厂）

目标：从“能生成”到“能发布”。

- 学习重点
  - 批量调度
  - 字幕与标题生成
  - 封面和剪辑自动化
- 交付物
  - 批处理输入（CSV/JSON）
  - 自动封面、标题、字幕
  - 发布前质检与结果归档

## 当前仓库落地建议

- 现有工作流文件可继续作为 Builder Agent 的模板来源
- 先锁定一个稳定工作流做基线（建议 img2video）
- 每次迭代只改一类变量：提示词、motion、采样参数三选一

## 验收标准

- 单次任务在 10 分钟内完成（含重试）
- QA 通过率 >= 70%
- 可稳定输出可发布短视频（5-8 秒）
