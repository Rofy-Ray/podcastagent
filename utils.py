import os
import asyncio
import requests

from tavily import AsyncTavilyClient
from state import PodcastSegment
from langsmith import traceable

def get_config_value(value):
    """
    Helper function to handle both string and enum cases of configuration values
    """
    return value if isinstance(value, str) else value.value

def deduplicate_and_format_sources(search_response, max_tokens_per_source, include_raw_content=True):
    """
    Takes a list of search responses and formats them into a readable string.
    Limits the raw_content to approximately max_tokens_per_source.
 
    Args:
        search_responses: List of search response dicts, each containing:
            - query: str
            - results: List of dicts with fields:
                - title: str
                - url: str
                - content: str
                - score: float
                - raw_content: str|None
        max_tokens_per_source: int
        include_raw_content: bool
            
    Returns:
        str: Formatted string with deduplicated sources
    """
    sources_list = []
    for response in search_response:
        sources_list.extend(response['results'])
    
    unique_sources = {source['url']: source for source in sources_list}

    formatted_text = "Sources:\n\n"
    for i, source in enumerate(unique_sources.values(), 1):
        formatted_text += f"Source {source['title']}:\n===\n"
        formatted_text += f"URL: {source['url']}\n===\n"
        formatted_text += f"Most relevant content from source: {source['content']}\n===\n"
        if include_raw_content:
            char_limit = max_tokens_per_source * 4
            raw_content = source.get('raw_content', '')
            if raw_content is None:
                raw_content = ''
                print(f"Warning: No raw_content found for source {source['url']}")
            if len(raw_content) > char_limit:
                raw_content = raw_content[:char_limit] + "... [truncated]"
            formatted_text += f"Full source content limited to {max_tokens_per_source} tokens: {raw_content}\n\n"
                
    return formatted_text.strip()

def format_segments(segments: list[PodcastSegment]) -> str:
   formatted_str = ""
   for idx, segment in enumerate(segments, 1):
       formatted_str += f"""
           {'='*60}
           Segment {idx}: {segment.title}
           {'='*60}
           Duration: {segment.duration}
           Description: {segment.description}
           Requires Research: {segment.research}

           Dialogue:
           {segment.dialogue if segment.dialogue else '[Not yet written]'}
       """
   return formatted_str

@traceable
async def tavily_search_async(search_queries):
    """
    Performs concurrent web searches using the Tavily API.

    Args:
        search_queries (List[SearchQuery]): List of search queries to process

    Returns:
            List[dict]: List of search responses from Tavily API, one per query. Each response has format:
                {
                    'query': str, 
                    'follow_up_questions': None,      
                    'answer': None,
                    'images': list,
                    'results': [                     
                        {
                            'title': str,            
                            'url': str,              
                            'content': str,          
                            'score': float,          
                            'raw_content': str|None  
                        },
                        ...
                    ]
                }
    """
    
    tavily_async_client = AsyncTavilyClient()
    
    search_tasks = []
    for query in search_queries:
            search_tasks.append(
                tavily_async_client.search(
                    query,
                    max_results=5,
                    include_raw_content=True,
                    topic="general"
                )
            )

    search_docs = await asyncio.gather(*search_tasks)

    return search_docs