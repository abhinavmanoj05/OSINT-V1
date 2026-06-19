import sys
import os

# Force UTF-8 encoding for standard streams on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.helpers import resolve_gravatar_profile, resolve_github_url_from_email, scrape_urls_concurrently

# Ensure the project root directory is in the path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agents.manager.manager_agent import run_manager
from agents.tool_discovery.tool_discovery_agent import discover_tools
from agents.correlation.correlation_agent import run_correlation

# Import individual tools to call them
from tools.sherlock_tool import username_osint
from tools.profile_scraper import scrape_profile
from tools.holehe_tool import email_osint
from tools.dns_tool import dns_lookup
from tools.whois_tool import whois_lookup
from tools.web_search_tool import web_search_persona

# -----------------------------
# TOOLS MAPPING
# -----------------------------
tool_map = {
    "username_osint": username_osint,
    "scrape_profile": scrape_profile,
    "email_osint": email_osint,
    "dns_lookup": dns_lookup,
    "whois_lookup": whois_lookup,
    "web_search_persona": web_search_persona
}

# -----------------------------
# INTERACTIVE INVESTIGATION SESSION
# -----------------------------
print("OSINT Interactive Investigation Session")
print("Type 'q' or 'quit' at the prompt to exit.")

session_history = []

while True:
    print("\n" + "="*50)
    query = input("Enter a query to start investigation (or 'q' to quit): ")
    query = query.strip('"\'\\')
    
    if query.lower() in ['q', 'quit']:
        print("Exiting session. Goodbye!")
        break
        
    if not query:
        continue

    # -----------------------------
    # CLASSIFY (OPTIONAL CONTEXT TAGGING)
    # -----------------------------
    def classify(query: str):
        if "@" in query:
            return "email"
        return "generic"

    query_type = classify(query)
    print("Detected type:", query_type)

    # -----------------------------
    # MULTI-AGENT EXECUTION PIPELINE (STATE MACHINE)
    # -----------------------------
    query_history = []
    max_steps = 10
    
    for step_idx in range(max_steps):
        print(f"\n--- Step {step_idx + 1} ---")
        print(f"[Orchestrator] Invoking Manager Agent...")
        
        try:
            decision = run_manager(query, query_history)
            print(f"[Orchestrator] Manager Decision: {decision}")
        except Exception as e:
            print(f"[Orchestrator] Manager Agent Error: {e}")
            decision = {
                "next_step": "tool_discovery" if not query_history else "correlation",
                "args": {
                    "task_type": "email_search" if query_type == "email" else "general_search"
                }
            }
            print(f"[Orchestrator] Falling back to: {decision}")
            
        next_step = decision.get("next_step")
        args = decision.get("args", {})
        
        # Programmatic Guardrail: Force progression to correlation if tool_discovery has already run
        has_discovered = any(item.get("action") == "tool_discovery" for item in query_history)
        if next_step == "tool_discovery" and has_discovered:
            print("[Orchestrator Guardrail] Tool discovery already executed. Forcing correlation step...")
            next_step = "correlation"
        
        if next_step == "tool_discovery":
            task_type = args.get("task_type", "username_search")
            print(f"[Orchestrator] Running Tool Discovery Agent for task '{task_type}'...")
            try:
                discovery_res = discover_tools(task_type, query)
                tool_names = discovery_res.get("tools", [])
            except Exception as e:
                print(f"[Orchestrator] Tool Discovery Error: {e}")
                fallback_tools = {
                    "username_search": ["username_osint"],
                    "email_search": ["email_osint"],
                    "domain_search": ["dns_lookup", "whois_lookup"],
                    "url_read": ["scrape_profile"],
                    "full_name_search": ["web_search_persona"],
                    "general_search": ["web_search_persona"]
                }
                tool_names = fallback_tools.get(task_type, ["username_osint"])
                
            outputs = []
            for tname in tool_names:
                if tname in tool_map:
                    print(f"  -> [Worker] Running {tname} with input '{query}'...")
                    try:
                        out = tool_map[tname].invoke(query)
                        outputs.append({"tool": tname, "output": out})
                    except Exception as e:
                        outputs.append({"tool": tname, "error": str(e)})
            
            # Automatic scraping enrichment phase for discovered profile links
            scraped_profiles = []
            resolved_details = []

            # 1. Handle Username Search Results
            for out_item in outputs:
                tname = out_item.get("tool")
                out_val = out_item.get("output")
                if tname == "username_osint" and isinstance(out_val, dict) and "results" in out_val:
                    discovered_urls = []
                    for item in out_val["results"]:
                        site = item.get("site", "").lower()
                        url = item.get("url", "")
                        if site in ["github", "medium", "allmylinks", "kick", "youtube", "pinterest", "mastodon"] and url:
                            discovered_urls.append((site, url))
                    
                    # Scrape all profiles, prioritizing github and medium first
                    discovered_urls.sort(key=lambda x: 0 if x[0] in ["github", "medium"] else 1)
                    urls_to_scrape = [url for site, url in discovered_urls]
                    if urls_to_scrape:
                        scraped_profiles.extend(scrape_urls_concurrently(urls_to_scrape))

            # 2. Handle Email Search Results
            if task_type == "email_search":
                print(f"  -> [Worker] Starting email profile resolution for '{query}'...")
                
                # Run Gravatar lookup
                grav_profile = resolve_gravatar_profile(query)
                if grav_profile:
                    resolved_details.append({
                        "source": "Gravatar",
                        "profile": grav_profile
                    })
                            
                # Run GitHub Commit API search
                github_url = resolve_github_url_from_email(query)
                if github_url:
                    resolved_details.append({
                        "source": "GitHub Commit Search",
                        "profile_url": github_url
                    })
                
                # Collect URLs to scrape
                urls_to_enrich = []
                if grav_profile:
                    urls_to_enrich.extend(grav_profile.get("urls", [])[:1])
                if github_url:
                    urls_to_enrich.append(github_url)
                
                # De-duplicate URLs
                urls_to_enrich = list(dict.fromkeys(urls_to_enrich))
                if urls_to_enrich:
                    scraped_profiles.extend(scrape_urls_concurrently(urls_to_enrich))

            query_history.append({
                "action": "tool_discovery",
                "task_type": task_type,
                "outputs": outputs,
                "resolved_details": resolved_details,
                "scraped_profiles": scraped_profiles
            })
                
        elif next_step == "correlation":
            # Append this query's discovery outputs to the global session_history
            for item in query_history:
                if item.get("action") == "tool_discovery":
                    session_history.append(item)
                    
            print(f"[Orchestrator] Running Correlation Agent to compile session intelligence report...")
            try:
                # Correlate across all session data gathered so far!
                report = run_correlation({"output": str(session_history)})
                query_history.append({
                    "action": "correlation",
                    "report": report
                })
            except Exception as e:
                print(f"[Orchestrator] Correlation Error: {e}")
                query_history.append({
                    "action": "correlation",
                    "error": str(e)
                })
            break
                
        else:
            print(f"[Orchestrator] Unknown step: {next_step}")
            break

    # Extract and display the report for this step
    step_report = None
    for hist_item in reversed(query_history):
        if hist_item.get("action") == "correlation" and "report" in hist_item:
            step_report = hist_item["report"]
            break

    print("\n================ SESSION RESULT ================\n")
    if step_report:
        import json
        import os
        
        # Ensure entities are sorted by confidence
        for key in ["confirmed_entities", "possible_entities"]:
            if key in step_report and isinstance(step_report[key], list):
                step_report[key].sort(key=lambda x: x.get("confidence_score", 0), reverse=True)
                
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