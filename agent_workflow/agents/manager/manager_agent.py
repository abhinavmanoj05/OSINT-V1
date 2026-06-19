from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from core.llm import get_llm

manager_prompt = ChatPromptTemplate.from_template("""
You are the central supervisor of an information collection system.
Your job is to decide the next step to execute based on the user's query and the history of actions completed so far.

Available steps to execute:
1. "tool_discovery": Run this first to map the query type (username, email, or domain) to search tools, execute them, and gather results.
2. "correlation": Run this once you have gathered all search results, to compile the final summary report.

Rules:
- You must always run "tool_discovery" first if no search has been done yet.
- Once search results are gathered and present in the history, call "correlation" to compile the final report.

Return JSON only:
{{
  "next_step": "tool_discovery | correlation",
  "args": {{
    "task_type": "username_search | email_search | domain_search | full_name_search | general_search"
  }}
}}

Query:
{query}

History of actions executed so far:
{history}
""")
llm = get_llm()
manager_chain = manager_prompt | llm | JsonOutputParser()


def run_manager(query: str, history: list) -> dict:
    return manager_chain.invoke({
        "query": query,
        "history": str(history)
    })