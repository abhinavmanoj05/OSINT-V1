from langchain_core.prompts import ChatPromptTemplate
from backend.agent_workflow.core.llm import get_llm
import json
import re

corr_prompt = ChatPromptTemplate.from_template("""
You are a senior Threat Intelligence Entity Resolution & Correlation Engine.

You receive raw search output results from multiple OSINT tools.

Your job:
1. **Entity Resolution:** Analyze the data and identify distinct, real-world entities (people, organizations, etc.). Extract all their potential footprints (usernames, real names, emails, domains, social profiles, etc.). Merge similar listings and remove duplicates.
2. **Entity Correlation:** Discover relationships between these resolved entities (e.g., studying at the same college, working at the same company) and generate a confidence score (0.0 to 1.0) for each entity based on cross-referencing.
- You MUST return a JSON object with strictly three keys:
  1. "narrative_summary": A detailed Markdown report describing the primary target. MUST include a beautifully formatted Markdown table (Profile Attribute | Details | Confidence Score) and bulleted sections for footprints and insights. Use Markdown tables, not raw ASCII text.
  2. "nodes": A list of extracted entities. Each node must have: "id" (unique string), "type" (e.g. Person, Email, Phone, Location, Username), and "attributes" (a dictionary of findings).
  3. "edges": A list of connections between nodes. Each edge must have: "source" (node id), "target" (node id), and "relation" (e.g. OWNS_EMAIL, LIVES_AT).

Format your nodes and edges like this:
"nodes": [
    {{ "id": "email1", "type": "Email", "attributes": {{ "email": "test@example.com" }} }},
    {{ "id": "person1", "type": "Person", "attributes": {{ "name": "John Doe", "confidence": 0.95 }} }}
],
"edges": [
    {{ "source": "person1", "target": "email1", "relation": "OWNS_EMAIL" }}
]

CRITICAL RULES FOR FOOTPRINTS & JSON DATA:
- ONLY include fields in `linked_data` if you have actual data for them. Omit the key if you don't.
- ALWAYS use `profile_url` (string) for the profile link, NOT `urls` (array).
- NEVER generate placeholder usernames like @GITHUB-PROFILE or @LINKEDIN-PROFILE. If you only see a link, try to extract the username from the URL, or omit the username field.
- Do NOT use generic website titles or random text as `persona_name`. It must be the person's real name or their primary online handle.
- Do NOT make up data.

CRITICAL JSON FORMATTING RULES:
1. Do NOT use unescaped double quotes inside strings. Use 'single quotes' or escape them as \".
2. Do NOT use unescaped newlines inside strings. Use \\n for newlines.
3. Ensure every key and value is properly quoted with double quotes.
4. Ensure commas separate items correctly.
Return ONLY a valid JSON object. DO NOT output Markdown blocks (no ```json). DO NOT output any reasoning or conversational text before or after the JSON.
DATA:
{data}
""")

def run_correlation(state):
    data = state.get("output", state)
    llm_model = state.get("llm_model") if isinstance(state, dict) else None
    llm = get_llm(model=llm_model)
    correlation_chain = corr_prompt | llm

    try:
        # We manually invoke the LLM to get raw text to avoid standard JsonOutputParser crashing on malformed JSON
        res = correlation_chain.invoke({"data": data})
        if not res or not res.content:
            raise ValueError("LLM returned empty output")
        
        raw_str = res.content

        # Extract JSON block between first { and last }
        match = re.search(r'\{.*\}', raw_str, re.DOTALL)
        if match:
            raw_str = match.group(0)

        # Remove markdown wrappers if any leaked through inside the braces
        raw_str = re.sub(r'^```json\s*', '', raw_str, flags=re.MULTILINE)
        raw_str = re.sub(r'^```\s*$', '', raw_str, flags=re.MULTILINE)

        # Replace python-style triple quotes hallucinated by the LLM
        raw_str = raw_str.replace('"""', '"')

        # Clean up trailing commas which break standard json parser
        raw_str = re.sub(r',\s*\}', '}', raw_str)
        raw_str = re.sub(r',\s*\]', ']', raw_str)

        # Let standard json.loads parse the string, allowing literal newlines via strict=False
        try:
            import json_repair
            parsed_json = json_repair.loads(raw_str.strip())
        except Exception as e_repair:
            print(f"[Correlation] json_repair fallback failed, trying native json: {e_repair}")
            parsed_json = json.loads(raw_str.strip(), strict=False)
            
        return parsed_json
    except Exception as e:
        print(f"[Correlation] Manual parsing failed: {e}")
        return {
            "narrative_summary": "Failed to parse AI correlation output. Data may have been malformed. Please check backend logs.",
            "nodes": [],
            "edges": []
        }