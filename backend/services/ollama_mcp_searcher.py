"""
Ollama + MCP OSINT Searcher
============================
Integrates new_version/ollama_mcp_client.py approach into the main backend.

- Checks if Ollama is running and the configured model is available
- Uses Ollama to intelligently select OSINT tools for a target identity
- Calls tools via the new_version/osint-tools-mcp-server over MCP stdio
- Returns structured OSINTFinding objects for the EntityProfiler pipeline
- Fails gracefully if Ollama or MCP server is unavailable
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

from backend.core.config import settings


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_mcp_server_path() -> Optional[str]:
    """Locate new_version/osint-tools-mcp-server/src/osint_tools_mcp_server.py"""
    override = (
        getattr(settings, "NEW_VERSION_MCP_SERVER_PATH", "")
        or os.environ.get("NEW_VERSION_MCP_SERVER_PATH", "")
    ).strip()
    if override and Path(override).exists():
        return override

    here = Path(__file__).resolve()
    for parent in [here.parent.parent.parent, here.parent.parent]:
        candidate = (
            parent / "new_version" / "osint-tools-mcp-server"
            / "src" / "osint_tools_mcp_server.py"
        )
        if candidate.exists():
            return str(candidate)

    print("[OllamaMCP] Warning: new_version MCP server script not found.")
    return None


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

async def _ollama_model_ready(host: str, model: str) -> bool:
    """Return True if Ollama is reachable and the model is pulled."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{host}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                available = [m.get("name", "") for m in data.get("models", [])]
                model_base = model.split(":")[0]
                for a in available:
                    if a == model or a.split(":")[0] == model_base:
                        return True
                print(
                    f"[OllamaMCP] Model '{model}' not found in Ollama.\n"
                    f"  Available: {available}\n"
                    f"  Fix: ollama pull {model}"
                )
                return False
    except Exception as exc:
        print(f"[OllamaMCP] Ollama not reachable at {host}: {exc}")
        return False


async def _ollama_chat(
    host: str,
    model: str,
    messages: list,
    tools: Optional[list] = None,
    timeout: int = 60,
) -> dict:
    """POST to /api/chat and return the response message dict."""
    import aiohttp
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }
    if tools:
        payload["tools"] = tools

    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{host}/api/chat",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("message", {})
            text = await resp.text()
            raise RuntimeError(f"Ollama chat error {resp.status}: {text[:300]}")


# ---------------------------------------------------------------------------
# MCP tool caller (stdio, same pattern as new_version/ollama_mcp_client.py)
# ---------------------------------------------------------------------------

async def _call_mcp_tool(
    server_script: str,
    tool_name: str,
    arguments: Dict[str, Any],
    timeout: int = 90,
) -> str:
    """Call one tool on the osint-tools-mcp-server via JSON-RPC stdio."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        return "[MCP SDK not installed — run: pip install mcp]"

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
        env=os.environ.copy(),
    )
    try:
        async with asyncio.timeout(timeout):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    parts = [
                        item.text
                        for item in result.content
                        if hasattr(item, "text")
                    ]
                    return "\n".join(parts)
    except TimeoutError:
        return f"[MCP] Timeout after {timeout}s calling {tool_name}"
    except Exception as exc:
        return f"[MCP] Error calling {tool_name}: {exc}"


# ---------------------------------------------------------------------------
# Result parsers
# ---------------------------------------------------------------------------

_SOURCE_MAP = {
    "sherlock_username_search": "sherlock_mcp",
    "holehe_email_search": "holehe_mcp",
    "maigret_username_search": "maigret_mcp",
    "blackbird_username_search": "blackbird_mcp",
    "ghunt_google_search": "ghunt_mcp",
    "spiderfoot_scan": "spiderfoot_mcp",
}


def _platform_from_line(line: str) -> str:
    bracket = re.search(r"\[([^\]]{2,40})\]", line)
    if bracket:
        return bracket.group(1).strip()
    colon = re.search(r"^([A-Za-z0-9\-_]{2,30}):", line)
    if colon:
        return colon.group(1).strip()
    return ""


def _parse_mcp_findings(
    tool_name: str,
    result_text: str,
    target_value: str,
    target_type: str,
) -> list:
    """Convert raw MCP tool output into OSINTFinding objects."""
    # Import here to avoid circular import at module level
    from backend.services.osint_engine import OSINTFinding, _platform_from_url

    findings = []
    try:
        data = json.loads(result_text)
    except json.JSONDecodeError:
        data = {"raw": result_text}

    if not isinstance(data, dict):
        data = {"raw": str(data)}

    if not data.get("success", True):
        print(f"[OllamaMCP] {tool_name} reported failure: {data.get('error', '??')}")
        return findings

    content = data.get("content", data.get("raw", ""))
    if isinstance(content, (dict, list)):
        # Sherlock might return a dict with "files" containing the CSVs
        if isinstance(content, dict) and "files" in content:
            file_contents = []
            for f in content.get("files", []):
                file_contents.append(f.get("content", ""))
            content_str = "\n".join(file_contents) + "\n" + str(content.get("stdout", ""))
        else:
            content_str = json.dumps(content)
    else:
        content_str = str(content)

    source = _SOURCE_MAP.get(tool_name, tool_name)
    found_count = 0

    # Clean escaped newlines if they exist
    content_str = content_str.replace('\\n', '\n')

    for line in content_str.splitlines():
        line = line.strip()
        if not line:
            continue
        
        # Find all URLs in the line (Sherlock CSV lines usually have 1, but just in case)
        url_matches = re.finditer(r"https?://[^\s,\"'\\]+", line)
        line_has_url = False
        
        for url_match in url_matches:
            url = url_match.group(0).rstrip(".,)")
            platform = _platform_from_url(url) or _platform_from_line(line)
            findings.append(OSINTFinding(
                source=source,
                entity_type=target_type,
                entity_value=target_value,
                platform=platform,
                url=url,
                confidence=0.82,
            ))
            found_count += 1
            line_has_url = True
            
        if not line_has_url and (
            "[+]" in line
            or "FOUND" in line.upper()
            or "claimed" in line.lower()
        ):
            platform = _platform_from_line(line)
            if platform:
                findings.append(OSINTFinding(
                    source=source,
                    entity_type=target_type,
                    entity_value=target_value,
                    platform=platform,
                    confidence=0.70,
                ))
                found_count += 1

    # Fallback: preserve raw output so LLM can still analyse it
    if found_count == 0 and content_str.strip():
        from backend.services.osint_engine import OSINTFinding
        findings.append(OSINTFinding(
            source=source,
            entity_type="raw_output",
            entity_value=target_value,
            platform=tool_name,
            confidence=0.40,
            metadata={"raw": content_str[:2000]},
        ))

    return findings


# ---------------------------------------------------------------------------
# Ollama tool definitions (same schema as new_version/ollama_mcp_client.py)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "sherlock_username_search",
            "description": "Search for username across 399+ social media platforms",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username to search"},
                    "timeout": {"type": "integer", "description": "Timeout seconds"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "holehe_email_search",
            "description": "Check if email is registered on 120+ platforms",
            "parameters": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "description": "Email address"},
                    "only_used": {"type": "boolean", "description": "Only registered accounts"},
                },
                "required": ["email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "maigret_username_search",
            "description": "Search for username across 3000+ sites",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Username to search"},
                },
                "required": ["username"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Main integration class
# ---------------------------------------------------------------------------

class OllamaMCPSearcher:
    """
    Integrates new_version Ollama+MCP workflow into the main EntityProfiler.

    This class mirrors what new_version/ollama_mcp_client.py does interactively,
    but runs it programmatically as part of the backend pipeline.
    """

    def __init__(self, llm_model: str = None):
        self.ollama_host: str = getattr(settings, "OLLAMA_HOST", "http://localhost:11434")
        self.ollama_model: str = llm_model or getattr(settings, "OLLAMA_MODEL", "qwen2.5:0.5b")
        self.mcp_server_path: Optional[str] = _resolve_mcp_server_path()
        self._ready: Optional[bool] = None  # lazy-checked on first use

    async def _check_ready(self) -> bool:
        if self._ready is None:
            mcp_ok = self.mcp_server_path is not None
            ollama_ok = await _ollama_model_ready(self.ollama_host, self.ollama_model)
            self._ready = mcp_ok and ollama_ok
            if not mcp_ok:
                print("[OllamaMCP] MCP server script not found — skipping Ollama-MCP layer.")
            if not ollama_ok:
                print(
                    f"[OllamaMCP] Ollama model '{self.ollama_model}' not ready — "
                    f"run: ollama pull {self.ollama_model}"
                )
        return self._ready

    async def search_identity(
        self,
        target_type: str,
        target_value: str,
        institution: str = "",
        location: str = "",
    ) -> list:
        """
        Run Ollama-driven MCP OSINT search and return List[OSINTFinding].
        Called from EntityProfiler.profile_target() after the main DDGS search.
        """
        if not await self._check_ready():
            return []

        print(f"[OllamaMCP] Searching {target_type}: '{target_value}'")

        ctx_lines = [
            f"Target type: {target_type}",
            f"Target value: {target_value}",
        ]
        if institution:
            ctx_lines.append(f"Institution: {institution}")
        if location:
            ctx_lines.append(f"Location: {location}")

        if target_type == "name":
            parts = target_value.lower().split()
            likely_usernames = []
            if len(parts) >= 2:
                likely_usernames.append("".join(parts))
                likely_usernames.append(parts[0] + parts[-1])
                likely_usernames.append(parts[0] + "_" + parts[-1])
            ctx_lines.append(f"CRITICAL: Sherlock requires usernames without spaces. Test these likely usernames: {', '.join(likely_usernames)}")

        messages = [
            {
                "role": "system",
                "content": (
                    "Select tools for target:\n"
                    "- username -> sherlock_username_search, maigret_username_search\n"
                    "- email    -> holehe_email_search\n"
                    "- name     -> sherlock_username_search (no spaces)\n"
                    "Call relevant tool then stop."
                )
            },
            {
                "role": "user",
                "content": "Investigate this target:\n" + "\n".join(ctx_lines),
            },
        ]

        all_findings: list = []

        for round_num in range(3):  # max 3 agentic rounds
            try:
                msg = await _ollama_chat(
                    self.ollama_host,
                    self.ollama_model,
                    messages,
                    tools=TOOL_DEFINITIONS,
                    timeout=60,
                )
            except Exception as exc:
                print(f"[OllamaMCP] Ollama chat error (round {round_num + 1}): {exc}")
                break

            messages.append(msg)
            tool_calls = msg.get("tool_calls", [])

            if not tool_calls and round_num == 0:
                print(f"[OllamaMCP] Model generated 0 tool calls. Forcing tool calls.")
                if target_type == "name" and "likely_usernames" in locals():
                    for lu in likely_usernames:
                        tool_calls.append({
                            "function": {"name": "sherlock_username_search", "arguments": {"username": lu}}
                        })
                elif target_type in ["username", "email"]:
                    tool_map = {"username": "sherlock_username_search", "email": "holehe_email_search"}
                    tool_calls.append({
                        "function": {"name": tool_map[target_type], "arguments": {target_type: target_value}}
                    })

            if not tool_calls:
                print(f"[OllamaMCP] Model completed after {round_num + 1} round(s).")
                break

            # Execute all tool calls concurrently
            call_tasks: list = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}
                
                # Sanitize arguments!
                if "username" in raw_args and isinstance(raw_args.get("username"), str):
                    raw_args["username"] = raw_args["username"].replace(" ", "").replace('"', '').replace("'", "")
                    
                call_tasks.append((tool_name, raw_args))

            # Force additional tools for 'name' if LLM missed them
            if target_type == "name" and "likely_usernames" in locals():
                existing_tools = [t for t, _ in call_tasks]
                # Force sherlock to run on all likely usernames if the LLM only picked maigret
                if "sherlock_username_search" not in existing_tools:
                    for lu in likely_usernames:
                        call_tasks.append(("sherlock_username_search", {"username": lu}))

            results = await asyncio.gather(
                *[
                    _call_mcp_tool(
                        self.mcp_server_path,
                        name,
                        args,
                        timeout=240,
                    )
                    for name, args in call_tasks
                ],
                return_exceptions=True,
            )

            for (tool_name, tool_args), raw_result in zip(call_tasks, results):
                if isinstance(raw_result, Exception):
                    result_text = f"Error: {raw_result}"
                    print(f"[OllamaMCP] {tool_name} raised: {raw_result}")
                else:
                    result_text = str(raw_result)

                # Determine what entity value this tool was called with
                inferred_type = (
                    "email" if "email" in tool_name
                    else "username" if "username" in tool_name
                    else target_type
                )
                inferred_value = (
                    tool_args.get("email")
                    or tool_args.get("username")
                    or tool_args.get("identifier")
                    or tool_args.get("domain")
                    or target_value
                )

                findings = _parse_mcp_findings(
                    tool_name, result_text, inferred_value, inferred_type
                )
                all_findings.extend(findings)
                print(
                    f"[OllamaMCP] {tool_name}({inferred_value!r}) "
                    f"-> {len(findings)} findings"
                )

                # Feed result back so model can continue if needed
                messages.append({
                    "role": "tool",
                    "content": result_text[:2000],
                })

        print(f"[OllamaMCP] Done — {len(all_findings)} total findings")
        return all_findings


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_searcher_instance: Optional[OllamaMCPSearcher] = None


def get_ollama_mcp_searcher(llm_model: str = None) -> OllamaMCPSearcher:
    """Return an OllamaMCPSearcher, bypassing singleton if model specified."""
    if llm_model:
        return OllamaMCPSearcher(llm_model=llm_model)
        
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = OllamaMCPSearcher()
    return _searcher_instance
