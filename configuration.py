import os
from enum import Enum
from dataclasses import dataclass, fields
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from dataclasses import dataclass

DEFAULT_PODCAST_STRUCTURE = """
Use this structure to create a 30-minute podcast dialogue:

1. Opening (2-3 minutes)
   - Host introduction (30 seconds)
   - Guest introduction (30-60 seconds)
   - Topic overview (1 minute)

2. Main Segments (24-25 minutes total)
   - 3-4 key discussion topics
   - Each segment 6-8 minutes
   
3. Closing (2-3 minutes)
   - Key takeaways (1 minute)
   - Guest final thoughts (30-60 seconds)
   - Host wrap-up (30 seconds)
"""

class SearchAPI(Enum):
    TAVILY = "tavily"

class PlannerProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"

class WriterProvider(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"

@dataclass(kw_only=True)
class Configuration:
    """The configurable fields for the chatbot."""
    podcast_structure: str = DEFAULT_PODCAST_STRUCTURE 
    number_of_queries: int = 15 
    max_search_depth: int = 4 
    planner_provider: PlannerProvider = PlannerProvider.OPENAI 
    planner_model: str = "gpt-4o"
    writer_provider: WriterProvider = WriterProvider.ANTHROPIC
    writer_model: str = "claude-3-5-sonnet-latest"
    search_api: SearchAPI = SearchAPI.TAVILY 

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )
        values: dict[str, Any] = {
            f.name: os.environ.get(f.name.upper(), configurable.get(f.name))
            for f in fields(cls)
            if f.init
        }
        return cls(**{k: v for k, v in values.items() if v})