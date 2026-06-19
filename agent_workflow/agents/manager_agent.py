from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from core.llm import get_llm

manager_prompt = ChatPromptTemplate.from_template("""
You are the central supervisor of an information collection system.
Your job is to decide the next step to execute based on the user's query and the history of actions completed so far.

Available steps to execute:
1. "tool_discovery": Run this to map the query type to OSINT tools, execute them, and gather raw data.
2. "scraper": Run this if the history indicates URLs were discovered that need scraping for deeper context.
3. "correlation": Run this once you have gathered all necessary OSINT and scraped data, to compile the final JSON report.

Rules:
- You must always run "tool_discovery" first if no search has been done yet.
- NEVER run "tool_discovery" more than once.
- If history contains the text "Found" (meaning URLs were extracted), you MUST set "next_step": "scraper".
- If history contains the text "No URLs found", you MUST skip scraper and set "next_step": "correlation".

Return ONLY a valid JSON object. DO NOT output Markdown blocks (no ```json). DO NOT output any reasoning or conversational text before or after the JSON.

{{
  "next_step": "tool_discovery | scraper | correlation",
  "args": {{
    "task_type": "username_search | email_search | domain_search | full_name_search | general_search"
  }}
}}

CRITICAL JSON FORMATTING RULES:
1. Do NOT use unescaped double quotes inside strings. Use 'single quotes' or escape them as \\".
2. Do NOT use unescaped newlines inside strings. Use \\n for newlines.
3. Ensure every key and value is properly quoted with double quotes.
4. Ensure commas separate items correctly.

Query:
{query}

History of actions executed so far:
{history}
""")
llm = get_llm()
parser = JsonOutputParser()
manager_chain = manager_prompt | llm | parser

def run_manager(query: str, history: list) -> dict:
    import json
    import re
    try:
        return manager_chain.invoke({
            "query": query,
            "history": str(history)
        })
    except Exception as e:
        print(f"[Manager Agent] Error parsing JSON: {e}. Forcing correlation.")
        return {
            "next_step": "correlation",
            "args": {"task_type": "general_search"}
        }