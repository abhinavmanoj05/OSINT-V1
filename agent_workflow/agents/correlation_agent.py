from langchain_core.prompts import ChatPromptTemplate
from core.llm import get_llm
import json
import re

corr_prompt = ChatPromptTemplate.from_template("""
You are a senior Threat Intelligence Correlation Engine.

You receive raw search output results from multiple OSINT tools.

Your job:
- Analyze the data and extract all potential entities (usernames, real names, emails, domains, social profiles, etc.).
- Generate a confidence score (0.0 to 1.0) for each entity based on cross-referencing.
- Merge similar listings and remove duplicates.
- You MUST return a JSON object with strictly three keys:
  1. "narrative_summary": A detailed Markdown report describing the primary target. MUST include a beautifully formatted Markdown table (Profile Attribute | Details | Confidence Score) and bulleted sections for footprints and insights. Use Markdown tables, not raw ASCII text.
  2. "confirmed_entities": A list of entities with a confidence score of 0.85 or higher.
  3. "possible_entities": A list of entities with a confidence score below 0.85.

Format each entity in the list as:
{{
   "persona_name": "...",
   "confidence": 0.95,
   "reasoning": "Why this matches",
   "linked_data": {{"urls": ["http..."]}}
}}

CRITICAL JSON FORMATTING RULES:
1. Do NOT use unescaped double quotes inside strings. Use 'single quotes' or escape them as \".
2. Do NOT use unescaped newlines inside strings. Use \\n for newlines.
3. Ensure every key and value is properly quoted with double quotes.
4. Ensure commas separate items correctly.
Return ONLY a valid JSON object. DO NOT output Markdown blocks (no ```json). DO NOT output any reasoning or conversational text before or after the JSON.
DATA:
{data}
""")

llm = get_llm()
correlation_chain = corr_prompt | llm

def run_correlation(state):
    data = state.get("output", state)

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
            "confirmed_entities": [],
            "possible_entities": []
        }