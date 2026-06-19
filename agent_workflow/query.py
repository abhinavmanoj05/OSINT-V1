import sys
import os

# Force UTF-8 encoding for standard streams on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure the project root directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api import execute_query

# -----------------------------
# INTERACTIVE INVESTIGATION SESSION
# -----------------------------
if __name__ == "__main__":
    print("OSINT Interactive Investigation Session")
    print("Type 'q' or 'quit' at the prompt to exit.")

    session_history = []

    while True:
        print("\n" + "="*50)
        query = input("Enter a query to start investigation (or 'q' to quit): ")
        query = query.strip('\"\'\\\\')
        
        if query.lower() in ['q', 'quit']:
            print("Exiting session. Goodbye!")
            break
            
        if not query:
            continue

        step_report, session_history = execute_query(query, session_history)

        print("\n================ SESSION RESULT ================\n")
        if step_report:
            import json
            import os
            
            print(json.dumps(step_report, indent=2))
            
            safe_query = query.replace(' ', '_').replace('/', '_')
            os.makedirs("reports", exist_ok=True)
            
            # Save raw session data
            with open(f"reports/{safe_query}_search_data.json", "w", encoding="utf-8") as f:
                json.dump(session_history, f, indent=4, default=str)
                
            # Save correlated entities
            with open(f"reports/{safe_query}_correlated_entities.json", "w", encoding="utf-8") as f:
                json.dump(step_report, f, indent=4, default=str)
                
            print(f"\n[+] Raw session data saved to reports/{safe_query}_search_data.json")
            print(f"[+] Correlated entities saved to reports/{safe_query}_correlated_entities.json")
        else:
            print("Investigation finished, but no session report could be compiled.")
