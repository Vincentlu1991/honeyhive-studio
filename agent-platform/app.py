from __future__ import annotations

import json

import streamlit as st

from multi_agent_video.chat_hub import create_runtime
from multi_agent_video.config import load_config
from multi_agent_video.models import SceneSpec


st.set_page_config(page_title="Multi-Agent Video Studio", layout="wide")
st.title("Multi-Agent AI Video Generation Platform")
st.caption("本地优先 | 成本控制 | 主管Agent统筹")

config = load_config()
runtime = create_runtime(config)

st.sidebar.header("运行模式")
st.sidebar.write(f"本地LLM启用: {config.enable_local_llm}")
st.sidebar.write(f"Provider: {config.local_llm_provider}")
st.sidebar.write(f"Model: {config.local_llm_model}")
st.sidebar.write(f"ComfyUI: {config.comfyui_base_url}")

st.sidebar.divider()
st.sidebar.header("Prompt 规则")
rules_summary = runtime.prompt_agent.get_rewrite_rules_summary()
st.sidebar.write(f"规则数量: {rules_summary.get('rule_count', 0)}")
if st.sidebar.button("♻️ 热重载 Prompt 规则"):
    loaded = runtime.prompt_agent.reload_rewrite_rules()
    st.sidebar.success(f"已重载，当前规则数: {loaded}")
tags = rules_summary.get("tags", [])
if tags:
    st.sidebar.caption("标签: " + ", ".join(tags))

if "agent_chats" not in st.session_state:
    st.session_state.agent_chats = {
        "supervisor": [],
        "story": [],
        "prompt": [],
        "builder": [],
        "qa": [],
    }


def render_chat(agent_key: str, reply_func):
    for role, msg in st.session_state.agent_chats[agent_key]:
        with st.chat_message(role):
            st.write(msg)

    user_msg = st.chat_input(f"和 {agent_key} agent 对话")
    if user_msg:
        st.session_state.agent_chats[agent_key].append(("user", user_msg))
        with st.chat_message("user"):
            st.write(user_msg)
        reply = reply_func(user_msg)
        st.session_state.agent_chats[agent_key].append(("assistant", reply))
        with st.chat_message("assistant"):
            st.write(reply)


col1, col2 = st.columns([1, 2])
with col1:
    st.subheader("Agent 总览")
    st.markdown("- Supervisor Agent: 统筹计划与成本")
    st.markdown("- Story Agent: 场景结构化")
    st.markdown("- Prompt Agent: 提示词工程")
    st.markdown("- Builder Agent: 工作流注入")
    st.markdown("- QA Agent: 质量评分")

with col2:
    tab_sup, tab_agents, tab_run = st.tabs(["主管Agent", "单Agent对话", "主管发起执行"])

    with tab_sup:
        render_chat("supervisor", runtime.supervisor_agent.chat)

    with tab_agents:
        selected = st.selectbox("选择Agent", ["story", "prompt", "builder", "qa"])

        def _reply(msg: str) -> str:
            if selected == "story":
                scene = runtime.story_agent.run(msg)
                return json.dumps(scene.model_dump(), ensure_ascii=False, indent=2)
            if selected == "prompt":
                scene = SceneSpec(scene=msg, action="walking", mood="cinematic")
                prompt_pack = runtime.prompt_agent.run(scene)
                return json.dumps(prompt_pack.model_dump(), ensure_ascii=False, indent=2)
            if selected == "builder":
                return (
                    "Builder Agent说明: 接收 PromptPack 与 seed，生成 workflow_request，"
                    "并在执行阶段注入 ComfyUI workflow。"
                )
            qa = runtime.qa_agent.run({"outputs": {"preview": {}}})
            return json.dumps(qa.model_dump(), ensure_ascii=False, indent=2)

        render_chat(selected, _reply)

    with tab_run:
        brief = st.text_area("场景输入", "赛博朋克少女站在雨夜，霓虹灯反射在积水路面")
        seed = st.number_input("seed", value=42, step=1)
        if st.button("由主管Agent统筹执行", type="primary"):
            pipeline = runtime.build_pipeline().build()
            try:
                result = pipeline.invoke(
                    {"user_brief": brief, "seed": int(seed), "retry_count": 0},
                    config={"recursion_limit": 80},
                )
                st.success("执行完成")
                st.write(runtime.supervisor_agent.summarize_run(result))

                st.subheader("主管决策面板")
                c1, c2 = st.columns(2)
                with c1:
                    supervision_plan = result.get("supervision_plan", {})
                    st.write(f"风险等级: {supervision_plan.get('risk', 'N/A')}")
                    st.write(f"复杂度: {supervision_plan.get('complexity', 'N/A')}")
                    st.write(f"成本档位: {supervision_plan.get('cost_tier', 'N/A')}")
                    st.write(f"自适应重试上限: {supervision_plan.get('adaptive_max_retries', 'N/A')}")
                with c2:
                    qa = result.get("qa_report", {})
                    st.write(f"问题标签: {', '.join(qa.get('issue_tags', [])) or 'N/A'}")
                    actions = qa.get("recommended_actions", [])
                    if actions:
                        st.write("建议动作:")
                        for action in actions[:3]:
                            st.write(f"- {action}")

                st.json(result)
            except Exception as exc:
                st.error(f"执行失败: {exc}")
