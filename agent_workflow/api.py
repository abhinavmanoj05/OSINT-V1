import sys
import os
import json

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from graph import run_custom_graph

def execute_query(query: str, session_history: list = None, context: str = "") -> tuple[dict, list]:
    print(f"[API] Initializing Custom Multi-Agent workflow for: {query}")
    result = run_custom_graph(query, context)
    final_report = result.get("final_report") or {}
    
    step_report = {
        "summary": final_report.get("narrative_summary", result.get("summary", "")),
        "confirmed_entities": final_report.get("confirmed_entities", []),
        "possible_entities": final_report.get("possible_entities", []),
        "opsec_warnings": final_report.get("opsec_warnings", []),
        "recommended_next_steps": final_report.get("recommended_next_steps", []),
        "agent_structured_data": final_report,
        "raw_data": result.get("raw_data", [])
    }
    
    # Save the physical JSON files to disk as requested
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, "resolved_entities.json"), "w", encoding="utf-8") as f:
        json.dump(step_report["confirmed_entities"], f, indent=4)
        
    with open(os.path.join(output_dir, "unresolved_entities.json"), "w", encoding="utf-8") as f:
        json.dump(step_report["possible_entities"], f, indent=4)
        
    history = session_history or []
    history.extend(result.get("history", []))
    
    return step_report, history
