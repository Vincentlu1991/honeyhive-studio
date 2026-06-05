"""Workflow configuration loader.

Loads workflow mappings from ../../config/workflow_mappings.json, enabling:
- Multi-workflow support without code changes
- Centralized node mapping configuration
- Parameter presets per workflow type
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


class WorkflowConfig:
    """Single workflow configuration."""
    
    def __init__(self, name: str, config_dict: dict[str, Any]) -> None:
        self.name = name
        self.description = config_dict.get("description", "")
        self.file_path = config_dict.get("file_path", "")
        self.node_mapping = config_dict.get("node_mapping", {})
        self.parameters = config_dict.get("parameters", {})
        self.tags = config_dict.get("tags", [])
    
    def __repr__(self) -> str:
        return f"<WorkflowConfig {self.name}: {self.description}>"
    
    def get_node_mapping(self) -> dict[str, str]:
        """Get node ID mapping (compatible with BuilderAgent)."""
        return {k: v for k, v in self.node_mapping.items() if v is not None}


class WorkflowConfigManager:
    """Manages all workflow configurations from ../../config/workflow_mappings.json."""
    
    def __init__(self, config_path: Optional[Path] = None) -> None:
        if config_path is None:
            # Default location relative to this file
            config_path = Path(__file__).parent / "../../config/workflow_mappings.json"
        
        self.config_path = Path(config_path)
        self.workflows: dict[str, WorkflowConfig] = {}
        self.defaults: dict[str, str] = {}
        
        self._load_config()
    
    def _load_config(self) -> None:
        """Load and parse ../../config/workflow_mappings.json."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Workflow config not found: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Load workflow definitions
        for name, config in data.get("workflows", {}).items():
            self.workflows[name] = WorkflowConfig(name, config)
        
        # Load defaults
        self.defaults = data.get("defaults", {})
    
    def get_workflow(self, workflow_name: str) -> WorkflowConfig:
        """Get a workflow config by name."""
        if workflow_name not in self.workflows:
            available = list(self.workflows.keys())
            raise ValueError(f"Workflow '{workflow_name}' not found. Available: {available}")
        return self.workflows[workflow_name]
    
    def get_preferred_workflow(self) -> WorkflowConfig:
        """Get the preferred workflow (from defaults)."""
        name = self.defaults.get("preferred_workflow", "sd15_simple")
        return self.get_workflow(name)
    
    def get_fallback_workflow(self) -> WorkflowConfig:
        """Get the fallback workflow (from defaults)."""
        name = self.defaults.get("fallback_workflow", "sd15_simple")
        return self.get_workflow(name)
    
    def list_workflows(self, tag: Optional[str] = None) -> list[WorkflowConfig]:
        """List all workflows, optionally filtered by tag."""
        workflows = list(self.workflows.values())
        if tag:
            workflows = [w for w in workflows if tag in w.tags]
        return sorted(workflows, key=lambda w: w.name)
    
    def workflow_to_builder_mapping(self, workflow_name: str) -> dict[str, str]:
        """Get node mapping suitable for BuilderAgent."""
        workflow = self.get_workflow(workflow_name)
        return workflow.get_node_mapping()
    
    def workflow_to_parameters(self, workflow_name: str) -> dict[str, Any]:
        """Get recommended parameters for a workflow."""
        workflow = self.get_workflow(workflow_name)
        return workflow.parameters.copy()
    
    def get_workflow_file_path(self, workflow_name: str) -> str:
        """Get file path for a workflow."""
        workflow = self.get_workflow(workflow_name)
        return workflow.file_path
    
    def suggest_workflow_by_tags(self, tags: list[str]) -> Optional[WorkflowConfig]:
        """Find best matching workflow by tags."""
        all_workflows = self.list_workflows()
        
        # Score workflows by tag match
        best_match = None
        best_score = 0
        
        for workflow in all_workflows:
            matches = len(set(tags) & set(workflow.tags))
            if matches > best_score:
                best_score = matches
                best_match = workflow
        
        return best_match


# Lazy-loaded singleton
_manager: Optional[WorkflowConfigManager] = None


def get_workflow_manager() -> WorkflowConfigManager:
    """Get or create the global workflow config manager."""
    global _manager
    if _manager is None:
        _manager = WorkflowConfigManager()
    return _manager


def reset_workflow_manager() -> None:
    """Reset the global manager (mainly for testing)."""
    global _manager
    _manager = None
