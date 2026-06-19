from typing import TypedDict, List, Dict, Any, Annotated
import operator
import json
import re

from langgraph.graph import StateGraph, END
from agents.manager_agent import run_manager
from agents.tool_discovery_agent import discover_tools
from agents.scraper_agent import agent as scraper_agent
from agents.correlation_agent import correlation_chain
from tools.tool_map import tool_map

class AgentState(TypedDict):
    query: str
    context: str
    history: Annotated[List[str], operator.add]
    raw_data: Annotated[List[str], operator.add]
    urls_to_scrape: List[str]
    next_step: str
    task_type: str
    final_report: Dict[str, Any]

def manager_node(state: AgentState):
    print("[Manager Agent] Thinking...")
    history = state.get("history", [])
    
    if not history:
        # Guarantee first pass always triggers tool discovery to prevent fast-skipping
        print("[Manager Agent] First pass detected. Forcing Tool Discovery...")
        next_step = "tool_discovery"
        task_type = "general_search"
        q = state.get("query", "")
        if "@" in q: task_type = "email_search"
        elif " " not in q and "." in q: task_type = "domain_search"
        elif " " not in q: task_type = "username_search"
        else: task_type = "full_name_search"
    else:
        print(f"[DEBUG] Manager sees history: {history}")
        res = run_manager(state["query"], history)
        next_step = res.get("next_step", "correlation")
        task_type = res.get("args", {}).get("task_type", "general_search")
        
    print(f"[Manager Agent] Decided next step: {next_step}")
    return {"next_step": next_step, "task_type": task_type}

def tool_discovery_node(state: AgentState):
    print("[Tool Discovery Agent] Selecting tools...")
    task_type = state.get("task_type", "general_search")
    res = discover_tools(task_type, state["query"])
    tools_to_run = res.get("tools", [])
    
    results = []
    urls_found = []
    
    # Execute the selected tools
    for t_name in tools_to_run:
        if t_name in tool_map:
            print(f"[Tool Execution] Running {t_name}...")
            try:
                # Most tools take 'target' or string input
                tool_res = tool_map[t_name].invoke(state["query"])
                results.append(f"Output from {t_name}: {tool_res}")
                
                # Extract any URLs from the output for the scraper
                urls = re.findall(r'https?://[^\s<>"\']+', str(tool_res))
                urls_found.extend([u for u in urls if u])
                print(f"[DEBUG] Found {len(urls)} URLs in {t_name} output.")
            except Exception as e:
                results.append(f"Error running {t_name}: {e}")

    # Remove dupes
    urls_found = list(set(urls_found))
    
    history_msg = f"Ran Tool Discovery for {task_type}. Executed: {tools_to_run}."
    if urls_found:
        history_msg += f" Found {len(urls_found)} URLs."
    else:
        history_msg += " No URLs found."
        
    return {
        "history": [history_msg],
        "raw_data": results,
        "urls_to_scrape": urls_found
    }

def scraper_node(state: AgentState):
    print("[Scraper Agent] Scraping discovered URLs...")
    urls = state.get("urls_to_scrape", [])
    
    if not urls:
        print("[Scraper Agent] No URLs to scrape.")
        return {"history": ["Ran Scraper (No URLs found)"]}
        
    results = []
    for url in urls[:5]: # Limit to top 5 to save time
        print(f"[Scraper Agent] Scraping {url}...")
        try:
            from langchain_core.messages import HumanMessage
            res = scraper_agent.invoke({"messages": [HumanMessage(content=f"Scrape this URL and extract text: {url}")]})
            results.append(f"Scrape {url}:\n{res['messages'][-1].content}")
        except Exception as e:
            results.append(f"Failed to scrape {url}: {e}")
            
    return {
        "history": [f"Ran Scraper on {len(urls)} URLs"],
        "raw_data": results
    }

def correlation_node(state: AgentState):
    print("[Correlation Agent] Analyzing data and building final report...")
    
    # Combine context and raw data
    all_data = f"INITIAL CONTEXT:\n{state['context']}\n\nRAW OSINT DATA:\n" + "\n---\n".join(state.get("raw_data", []))
    
    from agents.correlation_agent import run_correlation
    final_json = run_correlation({"output": all_data})
    return {"final_report": final_json, "history": ["Ran Correlation"]}


def route_manager(state: AgentState):
    step = state.get("next_step")
    if step == "tool_discovery":
        return "tool_discovery"
    elif step == "scraper":
        return "scraper"
    elif step == "finish":
        return "__end__"
    else:
        return "correlation"

# Build the Graph
workflow = StateGraph(AgentState)

workflow.add_node("manager", manager_node)
workflow.add_node("tool_discovery", tool_discovery_node)
workflow.add_node("scraper", scraper_node)
workflow.add_node("correlation", correlation_node)

workflow.set_entry_point("manager")

workflow.add_conditional_edges(
    "manager",
    route_manager,
    {
        "tool_discovery": "tool_discovery",
        "scraper": "scraper",
        "correlation": "correlation",
        "__end__": END
    }
)

# True ReAct loop: all tools return control back to the manager, except correlation which ends it
workflow.add_edge("tool_discovery", "manager")
workflow.add_edge("scraper", "manager")
workflow.add_edge("correlation", END)

custom_graph = workflow.compile()

def run_custom_graph(query: str, context: str = "") -> dict:
    initial_state = {
        "query": query,
        "context": context,
        "history": [],
        "raw_data": [],
        "urls_to_scrape": [],
        "final_report": {}
    }
    
    final_state = custom_graph.invoke(initial_state)
    
    return {
        "summary": "Agent workflow complete. Custom multi-agent reasoning applied.",
        "history": final_state.get("history", []),
        "final_report": final_state.get("final_report", {}),
        "raw_data": final_state.get("raw_data", [])
    }
