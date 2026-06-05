from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multi_agent_video.agents import (
    ComfyUIBuilderAgent,
    ImageAnalysisAgent,
    ProductionPlannerAgent,
    PromptEngineerAgent,
    StoryAgent,
    SupervisorAgent,
    VideoQAAgent,
)
from multi_agent_video.config import AppConfig
from multi_agent_video.graph import VideoPipeline
from multi_agent_video.local_llm import LocalLLM, LocalLLMConfig
from multi_agent_video.shared_capabilities import SharedCapabilitiesService


@dataclass
class AgentRuntime:
    config: AppConfig
    llm: LocalLLM | None
    image_agent: ImageAnalysisAgent
    production_planner_agent: ProductionPlannerAgent
    story_agent: StoryAgent
    prompt_agent: PromptEngineerAgent
    builder_agent: ComfyUIBuilderAgent
    qa_agent: VideoQAAgent
    supervisor_agent: SupervisorAgent
    shared_capabilities: SharedCapabilitiesService

    def build_pipeline(self) -> VideoPipeline:
        return VideoPipeline(
            config=self.config,
            image_agent=self.image_agent,
            production_planner_agent=self.production_planner_agent,
            story_agent=self.story_agent,
            prompt_agent=self.prompt_agent,
            builder_agent=self.builder_agent,
            qa_agent=self.qa_agent,
            supervisor_agent=self.supervisor_agent,
            shared_capabilities=self.shared_capabilities,
        )


def create_runtime(config: AppConfig) -> AgentRuntime:
    llm = None
    if config.enable_local_llm:
        llm_config = LocalLLMConfig(
            provider=config.local_llm_provider,
            base_url=config.local_llm_base_url,
            model=config.local_llm_model,
            timeout_seconds=config.local_llm_timeout_seconds,
            max_retries=2,
        )
        llm = LocalLLM(llm_config)

    story_agent = StoryAgent(llm=llm)
    image_agent = ImageAnalysisAgent(llm=llm)
    production_planner_agent = ProductionPlannerAgent(llm=llm)
    prompt_agent = PromptEngineerAgent(
        llm=llm,
        enable_online_research=config.enable_online_research,
        online_research_base_url=config.online_research_base_url,
        online_research_timeout_seconds=config.online_research_timeout_seconds,
        online_research_max_results=config.online_research_max_results,
    )
    builder_agent = ComfyUIBuilderAgent()
    qa_agent = VideoQAAgent(llm=llm)
    supervisor_history_path = str(Path(config.output_dir) / "supervisor_history.jsonl")
    supervisor_agent = SupervisorAgent(llm=llm, history_file=supervisor_history_path)
    shared_capabilities = SharedCapabilitiesService(llm=llm)

    return AgentRuntime(
        config=config,
        llm=llm,
        image_agent=image_agent,
        production_planner_agent=production_planner_agent,
        story_agent=story_agent,
        prompt_agent=prompt_agent,
        builder_agent=builder_agent,
        qa_agent=qa_agent,
        supervisor_agent=supervisor_agent,
        shared_capabilities=shared_capabilities,
    )
