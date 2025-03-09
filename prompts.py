podcast_planner_query_writer_instructions="""You are an expert technical writer, helping to plan a podcast. 

<Podcast topic>
{topic}
</Podcast topic>

<Podcast organization>
{podcast_organization}
</Podcast organization>

<Task>
Your goal is to generate {number_of_queries} search queries that will help gather comprehensive information for planning the podcast segments. 

The queries should:

1. Be related to the topic of the podcast
2. Research industry latest news and trends
3. Help satisfy the requirements specified in the podcast organization

Make the queries specific enough to find high-quality, relevant sources while covering the breadth needed for the podcast structure.
</Task>
"""

podcast_planner_instructions = """I want a plan for a podcast episode.

<Task>
Generate a list of segments for the podcast.

Each segment should have:
- Title - Engaging name for this segment
- Duration - Approximate length in minutes
- Description - Key points to cover
- Research - Whether to perform web research
- Dialogue - To be populated later with host-guest conversation

Opening and closing segments don't require research as they'll summarize the discussion.
</Task>

<Topic>
{topic}
</Topic>

<Podcast structure>
{podcast_structure}
</Podcast structure>

<Context>
{context}
</Context>
"""

query_writer_instructions="""You are an expert technical writer crafting targeted web search queries that will gather comprehensive information for writing a technical podcast segment.

<Segment topic>
{segment_topic}
</Segment topic>

<Task>
Your goal is to generate {number_of_queries} search queries that will help gather comprehensive information above the segment topic. 

The queries should:

1. Be related to the topic 
2. Examine different aspects of the topic
3. Find industry latest news

Make the queries specific enough to find high-quality, relevant sources.
</Task>
"""

dialogue_writer_instructions = """You are an expert podcast scriptwriter creating natural dialogue between a host and guest.

<Segment topic>
{segment_topic}
</Segment topic>

<Research material>
{context}
</Research material>

<Format>
{host_name}: <dialogue>
{guest_name}: <dialogue>

Use natural conversation markers:
- Brief pauses: ...
- Emphasis: *word*
- Interruptions: --
- Agreement: "Mm-hmm", "Right", "Exactly"
</Format>

<Style guidelines>
- Keep exchanges to 2-3 sentences
- Include relevant personal anecdotes
- Use conversational language
- Maintain technical accuracy
- Include occasional humor/banter
- End segments with smooth transitions
</Style guidelines>

<Formatting rules>
- Do NOT include:
  - Descriptive actions in *brackets* or any other formatting
  - Stage directions 
  - Non-spoken performance notes
- ONLY include:
  - Spoken dialogue
  - Minimal, relevant action descriptions that can be read aloud
  - Natural conversational elements
</Formatting rules>

<Quality checks>
- Natural flow between speakers
- Clear explanation of technical concepts
- Balanced speaking time
- Engaging dialogue
</Quality checks>
"""

transcript_optimizer_instructions = """Review and optimize a podcast segment transcript:

<segment transcript>
{transcript}
</segment transcript>

<task>
Evaluate for:
- Natural conversation flow
- Clear explanations
- Engaging delivery
- Smooth transitions

Suggest specific improvements for any issues found.
</task>

<format>
  grade: Literal["pass","fail"]
  improvement_suggestions: List[str]
  revised_transcript: Optional[str]
</format>
"""

final_segment_writer_instructions = """Create opening/closing podcast segments that tie the episode together.

<Segment type>
{segment_type}
</Segment type>

<Episode content>
{context}
</Episode content>

<Task>
For Opening:
- Host welcomes audience
- Introduces guest and credentials
- Sets up episode topic
- Duration: 2-3 minutes

For Closing:
- Summarize key insights
- Guest final thoughts
- Host wrap-up
- Call-to-action
- Duration: 2-3 minutes

Writing approach:
- Natural conversation
- Clear transitions
- Engaging hooks
</Task>
"""