# Hermes + Obsidian + LLM Wiki 知识库架构

## 目标

为 HoneyHive Studio 提供可检索、可维护、可注入的统一知识层：

- Hermes：流程技能化，沉淀可执行经验
- Obsidian：文档维护中台（面向人）
- LLM Wiki：检索注入层（面向模型）

## 目录分层

- docs/: 人类知识主库（策略、流程、安全、计划）
- output/skills/: 角色专属技能（执行规则）
- output/wiki/knowledge_index.json: 检索索引（模型使用）
- output/wiki/knowledge_state.json: 索引增量状态

## 配置文件

- agent-platform/config/wiki_knowledge_config.json

关键字段：

- sources: 索引数据源（docs、skills、CLAUDE.md）
- chunk: 分块参数（max_chars、overlap_chars）
- retrieval: 注入参数（top_k、max_context_chars、min_score）
- weights: 打分权重（关键词、角色匹配、团队匹配）

## 构建命令

在 agent-platform 目录下执行：

```powershell
.\.venv\Scripts\python.exe scripts\build-knowledge-index.py
```

角色覆盖率报告：

```powershell
.\.venv\Scripts\python.exe scripts\wiki-role-coverage-report.py
```

质量抽样评测（严格模式）：

```powershell
.\.venv\Scripts\python.exe scripts\wiki-quality-eval.py --min-pass-rate 0.75 --strict
```

Nightly 全流程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/nightly-knowledge.ps1 -Root . -MinPassRate 0.75
```

## 注入策略

- 主管对话：优先命中主管自身 + 团队角色相关知识
- 员工对话：优先命中员工专属技能 + docs 中相关片段
- 所有检索片段附 source_path，保证可追溯

## 维护流程

1. 在 Obsidian 编辑 docs
2. 更新/新增 output/skills 角色技能
3. 运行 build-knowledge-index.py 重建索引
4. 在 GUI 中通过主管/员工对话验证命中片段

## 质量门建议

- 文档变更后必须重建索引
- 角色技能变更后必须验证 staff_skill_files 映射
- 每周检查索引体量与命中质量
- 每日 Nightly 执行覆盖率报告和质量抽样评测
