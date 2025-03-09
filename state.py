from typing import Annotated, List, Literal, TypedDict, Optional
from pydantic import BaseModel, Field
import operator

class PodcastSegment(BaseModel):
    title: str = Field(description="Title for this segment of the podcast")
    duration: str = Field(description="Approximate duration in seconds")
    description: str = Field(description="Topics and concepts to cover")
    research: bool = Field(description="Whether to perform web research")
    dialogue: str = Field(description="The host-guest conversation script")

class Segments(BaseModel):
    segments: List[PodcastSegment] = Field(description="Segments of the podcast")

class SearchQuery(BaseModel):
    search_query: str = Field(None, description="Query for web search.")

class Queries(BaseModel):
    queries: List[SearchQuery] = Field(description="List of search queries.",)

class DialogueFeedback(BaseModel):
    grade: Literal["pass","fail"] = Field(
        description="Evaluation result indicating whether the dialogue meets requirements"
    )
    improvement_suggestions: List[str] = Field(description="Suggested improvements")
    revised_transcript: Optional[str] = Field(description="Revised dialogue if needed")
    follow_up_queries: List[SearchQuery] = Field(description="Additional research queries if needed")

class PodcastStateInput(TypedDict):
    topic: str
    host: str
    guest: str
    
class PodcastStateOutput(TypedDict):
    final_transcript: str

class PodcastState(TypedDict):
    topic: str
    host: str
    guest: str
    feedback_on_podcast_plan: str
    segments: list[PodcastSegment]
    completed_segments: Annotated[list, operator.add]
    episode_segments_from_research: str
    final_transcript: str

class SegmentState(TypedDict):
    segment: PodcastSegment
    search_iterations: int
    search_queries: list[SearchQuery]
    source_str: str
    episode_segments_from_research: str
    completed_segments: list[PodcastSegment]
    host: str
    guest: str 

class SegmentOutputState(TypedDict):
    completed_segments: list[PodcastSegment] 