"""
LLM Comprehension Layer for OSINT Analysis
==========================================
Primary: Ollama (local, zero-cost, offline capable)
Backdoor: OpenAI-compatible API, Google Gemini (optional fallbacks)

Provider selection is controlled by the LLM_PROVIDER env variable, but defaults to 'ollama'.
"""

import json
import os
import re
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from backend.core.config import settings


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

ENTITY_EXTRACTION_PROMPT = """Extract info to JSON. 
ONLY JSON. No text.

TARGET: {target_type} = "{target_value}"
CORPUS: {corpus}

JSON:
{{
  "name": [], "username": [], "email": [], "phone_number": [],
  "upi_id": [], "bank_account_id": [], "crypto_wallet": [],
  "ip_address": [], "domain": [], "modus_operandi": [],
  "locations": [], "affiliations": [], "key_findings": []
}}
"""

PROFILE_COMPREHENSION_PROMPT = """Analyze and return JSON. 
ONLY JSON. No text.

TARGET: {target_type} = "{target_value}"
ENTITIES: {entities}
PLATFORMS: {platforms}

JSON:
{{
  "behavioral_profile": {{
    "activity": "LOW/HIGH",
    "footprint": "SMALL/BIG",
    "persona": "STABLE/VARIED"
  }},
  "identity_confidence": {{ "score": 0.0, "reasoning": "" }},
  "threat_indicators": [],
  "recommended_steps": [],
  "key_findings": []
}}
"""

DOCUMENT_ANALYSIS_PROMPT = """Analyze the following document text and extract intelligence into JSON.
ONLY JSON. No text.

CORPUS: {corpus}

JSON FORMAT:
{{
  "related_entities": {{
    "names": [],
    "organizations": [],
    "handles": [],
    "financial_assets": [],
    "tech_assets": []
  }},
  "targets_identified": [
    {{
      "name": "Target Name",
      "role": "Subject/Suspect/Victim/Other",
      "context": "Why are they mentioned?"
    }}
  ],
  "topics_and_themes": {{
    "crimes": [],
    "events": [],
    "categories": [],
    "main_themes": []
  }},
  "summary": "Brief summary of the document"
}}
"""


# ---------------------------------------------------------------------------
# LLM Provider base class
# ---------------------------------------------------------------------------

class LLMProvider:
    """Abstract base for LLM providers."""

    async def complete(self, prompt: str, max_tokens: int = 4096, format: Optional[str] = None) -> str:
        raise NotImplementedError

    async def extract_entities(
        self,
        corpus: str,
        target_type: str,
        target_value: str,
        institution: str = "",
        location: str = ""
    ) -> Dict[str, Any]:
        """Use LLM to intelligently extract entities from corpus text."""
        # Truncate corpus to avoid token limits
        truncated = corpus[:24000] if len(corpus) > 24000 else corpus
        prompt = ENTITY_EXTRACTION_PROMPT.format(
            target_type=target_type,
            target_value=target_value,
            institution=institution,
            location=location,
            corpus=truncated
        )
        raw = await self.complete(prompt, max_tokens=3000, format="json")
        return _parse_json_response(raw)

    async def comprehend_profile(
        self,
        target_type: str,
        target_value: str,
        entities: Dict,
        source_platforms: List[str],
        tool_summary: str
    ) -> Dict[str, Any]:
        """Generate behavioral profile and threat assessment via LLM."""
        prompt = PROFILE_COMPREHENSION_PROMPT.format(
            target_type=target_type,
            target_value=target_value,
            entities=json.dumps(entities, indent=2)[:3000],
            platforms=", ".join(source_platforms),
            tool_summary=tool_summary[:2000]
        )
        raw = await self.complete(prompt, max_tokens=2000, format="json")
        parsed = _parse_json_response(raw)
        
        # Ensure default structure so frontend always renders
        if "behavioral_profile" not in parsed:
            parsed["behavioral_profile"] = {}
        if "threat_indicators" not in parsed:
            parsed["threat_indicators"] = []
        if "identity_confidence" not in parsed:
            parsed["identity_confidence"] = {"score": 0.0, "reasoning": ""}
            
        if not parsed.get("narrative_summary"):
            try:
                print(f"[LLM] JSON narrative summary empty. Running secondary text prompt fallback.")
                narrative_prompt = f"Write a 3-paragraph detailed investigative narrative summary for {target_type} '{target_value}' based on these findings:\n{json.dumps(entities)[:2000]}\nProvide ONLY the text summary."
                fallback_text = await self.complete(narrative_prompt, max_tokens=1000)
                parsed["narrative_summary"] = fallback_text.strip("`").replace("json\n", "")
            except Exception as e:
                print(f"[LLM] Narrative summary fallback failed: {e}")
                parsed["narrative_summary"] = "AI behavioral profiling failed or timed out."
                
        return parsed

    async def analyze_document(self, text: str) -> Dict[str, Any]:
        """Use LLM to perform deep semantic analysis of document text."""
        # Truncate text to avoid token limits
        truncated = text[:24000] if len(text) > 24000 else text
        prompt = DOCUMENT_ANALYSIS_PROMPT.format(corpus=truncated)
        raw = await self.complete(prompt, max_tokens=3000, format="json")
        parsed = _parse_json_response(raw)
        
        # Ensure default structure
        if "related_entities" not in parsed:
            parsed["related_entities"] = {}
        if "targets_identified" not in parsed:
            parsed["targets_identified"] = []
        if "topics_and_themes" not in parsed:
            parsed["topics_and_themes"] = {}
            
        return parsed


# ---------------------------------------------------------------------------
# Provider 1: Google Gemini (PRIMARY)
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """
    Google Gemini via google-generativeai SDK.
    Supports: gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-exp
    """

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model or getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")
        self._initialized = False

    def _init(self):
        if not self._initialized:
            try:
                import google.generativeai as genai
                if not self.api_key:
                    raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
                genai.configure(api_key=self.api_key)
                self._genai = genai
                self._model = genai.GenerativeModel(self.model_name)
                self._initialized = True
            except ImportError:
                raise RuntimeError(
                    "google-generativeai package not installed. "
                    "Run: pip install google-generativeai"
                )

    async def complete(self, prompt: str, max_tokens: int = 4096, format: Optional[str] = None) -> str:
        self._init()
        loop = asyncio.get_running_loop()
        generation_config = {
            "max_output_tokens": max_tokens,
            "temperature": 0.1,
        }
        if format == "json":
            generation_config["response_mime_type"] = "application/json"

        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._model.generate_content(
                    prompt,
                    generation_config=self._genai.types.GenerationConfig(**generation_config)
                )
            )
            return response.text
        except Exception as e:
            print(f"[Gemini] Error: {e}")
            raise


# ---------------------------------------------------------------------------
# Provider 2: OpenAI-compatible API (BACKDOOR A)
# ---------------------------------------------------------------------------
# Works with:
#   - OpenAI (OPENAI_API_KEY + OPENAI_BASE_URL=https://api.openai.com/v1)
#   - Groq  (OPENAI_API_KEY=<groq_key> + OPENAI_BASE_URL=https://api.groq.com/openai/v1)
#   - Together.ai (similar override)
#   - LM Studio (OPENAI_BASE_URL=http://localhost:1234/v1, no key needed)
#   - Any OpenAI-compatible local server

class OpenAICompatibleProvider(LLMProvider):
    """
    OpenAI-compatible provider. Set LLM_PROVIDER=openai in .env.
    Env vars: OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None
    ):
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "sk-dummy")
        self.base_url = base_url or getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model_name = model or getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")

    async def complete(self, prompt: str, max_tokens: int = 4096, format: Optional[str] = None) -> str:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            
            kwargs = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an elite data intelligence analyst. Return only valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }
            if format == "json" and "gpt" in self.model_name:
                kwargs["response_format"] = {"type": "json_object"}

            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except ImportError:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            )
        except Exception as e:
            print(f"[OpenAI-compat] Error: {e}")
            raise


# ---------------------------------------------------------------------------
# Provider 3: Ollama (BACKDOOR B — local, offline, zero-cost)
# ---------------------------------------------------------------------------
# Requires Ollama running locally: https://ollama.ai
# Model examples: llama3.1, mistral, mixtral, phi3, gemma2, qwen2
# Set LLM_PROVIDER=ollama and OLLAMA_MODEL=llama3.1 in .env

class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider. Zero-cost, fully offline capable.
    Install: https://ollama.ai
    Pull model: ollama pull qwen2.5
    Set LLM_PROVIDER=ollama, OLLAMA_HOST=http://localhost:11434, OLLAMA_MODEL=qwen2.5
    """

    def __init__(self, host: str = None, model: str = None):
        self.host = host or getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
        self.model_name = model or getattr(settings, "OLLAMA_MODEL", "qwen2.5")

    async def health_check(self) -> bool:
        """Check if Ollama server is reachable and the model is available."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.host}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                        model_base = self.model_name.split(":")[0]
                        if model_base not in models:
                            print(
                                f"[Ollama] WARNING: Model '{self.model_name}' not found locally.\n"
                                f"  Available: {models}\n"
                                f"  Pull it with: ollama pull {self.model_name}"
                            )
                        else:
                            print(f"[Ollama] ✓ Model '{self.model_name}' ready.")
                        return True
            return False
        except Exception:
            return False

    async def _ensure_model(self):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name") for m in data.get("models", [])]
                        model_base = self.model_name
                        if ":" not in model_base:
                            model_base = f"{model_base}:latest"
                        
                        if self.model_name not in models and model_base not in models:
                            print(f"[Ollama] Model '{self.model_name}' not found locally. Pulling now...")
                            async with session.post(
                                f"{self.host}/api/pull",
                                json={"name": self.model_name},
                                timeout=aiohttp.ClientTimeout(total=600)
                            ) as pull_resp:
                                if pull_resp.status != 200:
                                    print(f"[Ollama] Warning: Pull failed with status {pull_resp.status}")
        except Exception as e:
            print(f"[Ollama] _ensure_model error: {e}")

    async def complete(self, prompt: str, max_tokens: int = 4096, format: Optional[str] = None) -> str:
        await self._ensure_model()
        import aiohttp
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1
            }
        }
        if format == "json":
            payload["format"] = "json"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("message", {}).get("content", "")
                    else:
                        text = await resp.text()
                        raise RuntimeError(f"Ollama error {resp.status}: {text}")
        except Exception as e:
            print(f"[Ollama] Error: {e}")
            raise


# ---------------------------------------------------------------------------
# Provider Factory
# ---------------------------------------------------------------------------

def get_llm_provider() -> Optional[LLMProvider]:
    """
    Returns the configured LLM provider.
    Always returns Ollama.
    """
    host = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
    model = getattr(settings, "OLLAMA_MODEL", "qwen2.5")
    print(f"[LLM] Using Ollama local model: {model} @ {host}")
    print(f"[LLM] (If not installed: https://ollama.ai | Pull: ollama pull {model})")
    return OllamaProvider(host=host, model=model)


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> Dict[str, Any]:
    """Extremely robust extraction for 0.5b models. Rescues text if JSON fails."""
    if not raw:
        return {}
    
    # Strip markdown and excessive whitespace
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    
    parsed = {}
    # 1. Try JSON
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            parsed = {"key_findings": [str(parsed)]}
    except json.JSONDecodeError:
        try:
            start, end = cleaned.find('{'), cleaned.rfind('}')
            if start != -1 and end != -1:
                parsed = json.loads(cleaned[start:end+1])
                if not isinstance(parsed, dict):
                    parsed = {"key_findings": [str(parsed)]}
        except Exception:
            pass

    if not isinstance(parsed, dict):
        parsed = {}

    # 2. Rescuing Findings: If no JSON findings, find bullets/numbers
    findings = parsed.get("key_findings", [])
    if not findings:
        # Regex for bullets or numbers
        bullets = re.findall(r"(?:^|\n)\s*[\-•*0-9.]+\s*(.+)", raw)
        if bullets:
            findings = [b.strip() for b in bullets if len(b.strip()) > 5]
    
    # 3. Last Resort: Sentence-based extraction (if still empty)
    if not findings:
        # Filter out lines that look like prompt text or JSON boilerplate
        lines = [l.strip() for l in raw.splitlines() if len(l.strip()) > 20]
        findings = [l for l in lines if not any(c in l for c in "{}[]") and "TARGET:" not in l]

    # 4. Final Cleanup
    clean_findings = []
    for f in findings:
        if not isinstance(f, str): continue
        # Strip common hallucinated prefixes
        f = re.sub(r"^(?:Assistant|Summary|Findings|Key Findings|Bullet \d+):\s*", "", f, flags=re.IGNORECASE)
        f = f.strip().strip("•-*\"' \n,")
        
        # Check for hallucinated prompt template regurgitations
        if "LOW/HIGH" in f or "SMALL/BIG" in f or "STABLE/VARIED" in f:
            continue
            
        if len(f) > 5 and "{" not in f and "}" not in f:
            clean_findings.append(f)
            
    parsed["key_findings"] = clean_findings[:10]
    
    # Scrub behavioral profile if it's just the template
    bp = parsed.get("behavioral_profile", {})
    if isinstance(bp, dict):
        for k in ["activity", "footprint", "persona"]:
            val = str(bp.get(k, "")).upper()
            if "LOW/HIGH" in val or "SMALL/BIG" in val or "STABLE/VARIED" in val or val == k.upper():
                bp[k] = "UNKNOWN"
        parsed["behavioral_profile"] = bp
        
    return parsed


# ---------------------------------------------------------------------------
# Singleton instance cache
# ---------------------------------------------------------------------------

_provider_instance: Optional[LLMProvider] = None
_provider_initialized = False


def get_provider_singleton() -> Optional[LLMProvider]:
    """Return a cached provider instance (one-time initialization)."""
    global _provider_instance, _provider_initialized
    if not _provider_initialized:
        _provider_instance = get_llm_provider()
        _provider_initialized = True
    return _provider_instance
