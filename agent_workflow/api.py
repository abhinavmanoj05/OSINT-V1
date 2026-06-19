import sys
import os
import json

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from react_agent import run_investigation_agent

def execute_query(query: str, session_history: list = None, context: str = "") -> tuple[dict, list]:
    print(f"[API] Initializing ReAct reasoning loop for: {query}")
    result = run_investigation_agent(query, context)
    
    step_report = {
        "summary": result["summary"],
        "confirmed_entities": [{"entity": query, "confidence_score": 0.9}],
        "possible_entities": []
    }
    
    # Merge history if any
    history = session_history or []
    history.extend(result["history"])
    
    return step_report, history
