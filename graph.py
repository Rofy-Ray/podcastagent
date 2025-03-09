from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig

from langgraph.constants import Send
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt, Command
from langchain_core.tools import tool

from state import PodcastStateInput, PodcastStateOutput, Segments, PodcastState, SegmentState, SegmentOutputState, Queries, DialogueFeedback
from prompts import podcast_planner_query_writer_instructions, podcast_planner_instructions, query_writer_instructions, dialogue_writer_instructions, transcript_optimizer_instructions, final_segment_writer_instructions
from configuration import Configuration
from utils import tavily_search_async, deduplicate_and_format_sources, format_segments, get_config_value

async def generate_podcast_plan(state: PodcastState, config: RunnableConfig):
    topic = state["topic"]
    host = state["host"]
    guest = state["guest"]
    configurable = Configuration.from_runnable_config(config)
    podcast_structure = configurable.podcast_structure
    number_of_queries = configurable.number_of_queries

    writer_model = init_chat_model(
        model=get_config_value(configurable.writer_model),
        model_provider=get_config_value(configurable.writer_provider),
        temperature=0
    )
    structured_llm = writer_model.with_structured_output(Queries)

    query_results = structured_llm.invoke([
        SystemMessage(content=podcast_planner_query_writer_instructions.format(
            topic=topic,
            podcast_organization=podcast_structure,
            number_of_queries=number_of_queries
        )),
        HumanMessage(content="Generate search queries for podcast research")
    ])

    search_results = await tavily_search_async([q.search_query for q in query_results.queries])
    source_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=500)

    structured_llm = writer_model.with_structured_output(Segments)
    podcast_segments = structured_llm.invoke([
        AIMessage(content=podcast_planner_instructions.format(
            topic=topic,
            podcast_structure=podcast_structure,
            context=source_str
        )),
        HumanMessage(content="Generate the podcast segments")
    ])
    
    non_research = [s for s in podcast_segments.segments if not s.research]

    return Command(
        goto=[
            Send("build_segment_with_research", {
                "segment": s,
                "search_iterations": 0,
                "host": host,
                "guest": guest
            }) for s in podcast_segments.segments if s.research
        ],
        update={"segments": podcast_segments.segments, "completed_segments": non_research}
    )
    
def generate_queries(state: SegmentState, config: RunnableConfig):
    """ Generate search queries for a report section """

    segment = state["segment"]

    configurable = Configuration.from_runnable_config(config)
    number_of_queries = configurable.number_of_queries

    writer_provider = get_config_value(configurable.writer_provider)
    writer_model_name = get_config_value(configurable.writer_model)
    writer_model = init_chat_model(model=writer_model_name, model_provider=writer_provider, temperature=0) 
    structured_llm = writer_model.with_structured_output(Queries)

    system_instructions = query_writer_instructions.format(segment_topic=segment.description, number_of_queries=number_of_queries)

    queries = structured_llm.invoke([SystemMessage(content=system_instructions)]+[HumanMessage(content="Generate search queries on the provided topic.")])

    return {"search_queries": queries.queries}

async def search_web(state: SegmentState, config: RunnableConfig):
    """ Search the web for each query, then return a list of raw sources and a formatted string of sources."""
    
    search_queries = state["search_queries"]

    configurable = Configuration.from_runnable_config(config)

    query_list = [query.search_query for query in search_queries]
    
    search_api = get_config_value(configurable.search_api)

    try:
        search_results = await tavily_search_async(query_list)
        source_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=500, include_raw_content=True)
    except Exception as e:
        raise ValueError(f"Unsupported search API: {configurable.search_api}")

    return {"source_str": source_str, "search_iterations": state["search_iterations"] + 1}

def write_dialogue(state: SegmentState, config: RunnableConfig) -> Command[Literal[END, "search_web"]]:
    segment = state["segment"]
    source_str = state["source_str"]
    host = state["host"]
    guest = state["guest"]
    
    configurable = Configuration.from_runnable_config(config)
    
    writer_model = init_chat_model(
        model=get_config_value(configurable.writer_model),
        model_provider=get_config_value(configurable.writer_provider),
        temperature=0.7  
    )

    dialogue = writer_model.invoke([
        SystemMessage(content=dialogue_writer_instructions.format(
            segment_topic=segment.description,
            context=source_str,
            host_name=host,
            guest_name=guest,
        )),
        HumanMessage(content="Generate podcast dialogue for this segment")
    ])
    
    segment.dialogue = dialogue.content

    structured_llm = writer_model.with_structured_output(DialogueFeedback)
    feedback = structured_llm.invoke([
        SystemMessage(content=transcript_optimizer_instructions.format(
            transcript=segment.dialogue
        )),
        HumanMessage(content="Review and optimize the dialogue")
    ])

    if feedback.grade == "pass" or state["search_iterations"] >= config.max_search_depth:
        return Command(
            update={"completed_segments": [segment]},
            goto=END
        )
    else:
        return Command(
            update={
                "search_queries": feedback.follow_up_queries,
                "segment": segment
            },
            goto="search_web"
        )

def write_intro_outro(state: PodcastState, config: RunnableConfig):
    segments = state["segments"]
    completed_segments = state.get("completed_segments", [])
    
    intro_segment = next((s for s in segments if s.title.lower() == "intro"), None)
    outro_segment = next((s for s in segments if s.title.lower() == "outro"), None)
    
    configurable = Configuration.from_runnable_config(config)
    
    writer_model = init_chat_model(
        model=get_config_value(configurable.writer_model),
        model_provider=get_config_value(configurable.writer_provider),
        temperature=0.7
    )
    
    new_completed = []
    episode_segments = format_segments(completed_segments)
    
    if intro_segment and intro_segment not in completed_segments:
        dialogue = writer_model.invoke([
            SystemMessage(content=final_segment_writer_instructions.format(
                segment_type="opening",
                context=episode_segments
            )),
            HumanMessage(content="Generate engaging intro dialogue")
        ])
        intro_segment.dialogue = dialogue.content
        new_completed.append(intro_segment)
    
    if outro_segment and outro_segment not in completed_segments:
        dialogue = writer_model.invoke([
            SystemMessage(content=final_segment_writer_instructions.format(
                segment_type="closing",
                context=episode_segments
            )),
            HumanMessage(content="Generate memorable outro dialogue")
        ])
        outro_segment.dialogue = dialogue.content
        new_completed.append(outro_segment)
    
    updated_completed = completed_segments + new_completed
    
    return {
        "completed_segments": updated_completed,
        "episode_segments_from_research": format_segments(updated_completed)
    }
    
def compile_final_transcript(state: PodcastState):
    segments = state["segments"]
    completed_segments = {s.title: s.dialogue for s in state.get("completed_segments", [])}
    
    missing = [s.title for s in segments if s.title not in completed_segments]
    if missing:
        raise ValueError(f"Missing processed segments: {', '.join(missing)}")

    for segment in segments:
        segment.dialogue = completed_segments[segment.title]
        
    final_transcript = "\n\n".join([s.dialogue for s in segments])
    return {"final_transcript": final_transcript}


segment_builder = StateGraph(SegmentState, output=SegmentOutputState)
segment_builder.add_node("generate_queries", generate_queries)
segment_builder.add_node("search_web", search_web) 
segment_builder.add_node("write_dialogue", write_dialogue)

segment_builder.add_edge(START, "generate_queries")
segment_builder.add_edge("generate_queries", "search_web")
segment_builder.add_edge("search_web", "write_dialogue")

podcast_builder = StateGraph(PodcastState, 
                          input=PodcastStateInput,
                          output=PodcastStateOutput,
                          config_schema=Configuration)

podcast_builder.add_node("generate_podcast_plan", generate_podcast_plan)
podcast_builder.add_node("build_segment_with_research", segment_builder.compile())
podcast_builder.add_node("write_intro_outro", write_intro_outro)
podcast_builder.add_node("compile_final_transcript", compile_final_transcript)

podcast_builder.add_edge(START, "generate_podcast_plan")
podcast_builder.add_conditional_edges(
   "generate_podcast_plan",
   lambda edges: (
       "build_segment_with_research"
       if edges.get("goto")
       else "write_intro_outro"
   )
)
podcast_builder.add_edge("build_segment_with_research", "write_intro_outro")
podcast_builder.add_edge("write_intro_outro", "compile_final_transcript")
podcast_builder.add_edge("compile_final_transcript", END)

graph = podcast_builder.compile()