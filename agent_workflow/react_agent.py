from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from core.llm import get_llm
from tools.tool_map import tool_map

def run_investigation_agent(query: str, context: str = "") -> dict:
    llm = get_llm()
    
    system_prompt = """You are an expert Data Analyst and Digital Researcher.
Your task is to investigate the given target using the available tools, reason about the findings, and gather as much correlated public data as possible.

You have tools for:
- username_osint: Username Research
- scrape_profile: Web Scraping and profile extraction
- email_osint: Email verification
- dns_lookup: DNS records
- whois_lookup: Domain registration info
- web_search_persona: Multi-vector Web Search

Process:
1. Review the initial context provided from the search engines.
2. Based on the target type and initial context, invoke the appropriate tools to gather deeper insights.
3. If you find URLs or social profiles, use 'scrape_profile' to extract text.
4. If you find emails, verify them with 'email_osint'.
5. Once you have a comprehensive profile, provide a final, detailed summary report containing:

IMPORTANT: Your final output MUST be in strict JSON format. Do not write text outside of the JSON block.
The JSON must follow this exact structure:
{
  "confirmed_entities": [
    {
      "persona_name": "Name",
      "confidence": 0.95,
      "linked_data": {"emails": [], "phones": [], "profiles": []},
      "reasoning": "Why are we confident this is the target?"
    }
  ],
  "possible_entities": [
    {
      "persona_name": "Name",
      "confidence": 0.40,
      "linked_data": {"emails": [], "phones": [], "profiles": []},
      "reasoning": "Why might this be related?"
    }
  ],
  "opsec_warnings": ["Warning 1"],
  "recommended_next_steps": ["Step 1"]
}

Remember to ALWAYS call a tool if you need more data. Only output the final JSON when you have exhausted useful tool queries.
"""
    
    tools = list(tool_map.values())
    
    try:
        # Create the ReAct agent graph without keyword modifiers to ensure compatibility across all langgraph versions
        agent = create_react_agent(llm, tools=tools)
    except Exception as e:
        print(f"[ReAct] Failed to initialize agent: {e}")
        return {"summary": f"Agent init failed: {e}", "history": []}
    
    msg_content = f"Investigation Target: {query}\n\nInitial Context / Search Results:\n{context}"
    # Inject the system prompt as a SystemMessage directly
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=msg_content)
    ]
    
    print(f"[ReAct Agent] Starting dynamic tool-calling loop for {query}...")
    try:
        result = agent.invoke({"messages": messages})
        final_msg = result["messages"][-1].content
        
        # Extract tool calls for history
        history = []
        for m in result["messages"]:
            if getattr(m, 'type', None) == "tool" or m.__class__.__name__ == "ToolMessage":
                history.append({
                    "action": "tool_execution",
                    "tool": m.name,
                    "outputs": [{"tool": m.name, "output": m.content}]
                })
        
        return {
            "summary": final_msg,
            "history": history
        }
    except Exception as e:
        print(f"[ReAct Agent] Execution error: {e}")
        return {"summary": f"Execution error: {e}", "history": []}
