"""
Prompt templates for PipelineIQ agents.

Each agent that uses an LLM has its own prompt module in this package.
"""

from backend.prompts.scoring_prompt import SCORING_SYSTEM_PROMPT, build_scoring_prompt

__all__ = [
    "SCORING_SYSTEM_PROMPT",
    "build_scoring_prompt",
]
