from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from core.llm import get_llm

corr_prompt = ChatPromptTemplate.from_template("""
You are a senior Threat Intelligence Correlation Engine.

You receive raw search output results from multiple OSINT tools.

Your job:
- Analyze the data and extract all potential entities (usernames, real names, emails, domains, social profiles, etc.).
- Generate a confidence score (0.0 to 1.0) for each entity based on cross-referencing.
- Merge similar listings and remove duplicates.
- You MUST return a JSON object with strictly two keys:
  1. "confirmed_entities": A list of entities with a confidence score of 0.85 or higher.
  2. "possible_entities": A list of entities with a confidence score below 0.85.

Format each entity in the list as:
{{
   "entity_name": "...",
   "confidence_score": 0.95,
   "justification": "Why this matches",
   "urls": ["http..."]
}}

DATA:
{data}
""")
llm = get_llm()
correlation_chain = corr_prompt | llm | JsonOutputParser()

def run_correlation(state):
    data = state.get("output", state)

    return correlation_chain.invoke({
        "data": data
    })