from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.agent_workflow.core.llm import get_llm

tool_prompt = ChatPromptTemplate.from_template("""
You are a Tool Discovery Agent.

Map task_type to required tools.

Rules:

domain_search → dns_lookup, whois_lookup  
email_search → email_osint, breach_data_search  
username_search → username_osint, github_osint  
url_read → scrape_profile  
full_name_search → web_search_persona
general_search → web_search_persona, reverse_image_search

Return JSON only:

{{
  "tools": ["tool1", "tool2"],
  "input": "{input}"
}}

Task:
{task_type}

Input:
{input}
""")
llm = get_llm()
tool_chain = tool_prompt | llm | JsonOutputParser()


def discover_tools(task_type: str, input_data: str):
    return tool_chain.invoke({
        "task_type": task_type,
        "input": input_data
    })