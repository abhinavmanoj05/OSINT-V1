"""
Extended OSINT Tool Wrappers — from osint-tools-mcp-server
==========================================================
Integrates: Maigret, Blackbird, GHunt, SpiderFoot
alongside the existing Sherlock & Holehe wrappers.

Each wrapper:
  - Runs the tool as a subprocess (same as MCP server approach)
  - Normalises output into List[OSINTFinding]
  - Gracefully handles tool-not-found (tool is optional)
"""

import asyncio
import json
import re
import shutil
import sys
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from backend.services.osint_engine import OSINTFinding


# ---------------------------------------------------------------------------
# Async subprocess helper (mirrors osint_tools_mcp_server.py)
# ---------------------------------------------------------------------------

async def _run_tool(
    command: List[str],
    cwd: Optional[str] = None,
    input_data: Optional[str] = None,
    timeout: int = 120
) -> tuple[str, str, int]:
    """Run an external OSINT tool as an async subprocess."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE if input_data else None
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_data.encode() if input_data else None),
            timeout=timeout
        )
        return (
            stdout.decode("utf-8", errors="ignore"),
            stderr.decode("utf-8", errors="ignore"),
            proc.returncode or 0
        )
    except asyncio.TimeoutError:
        print(f"[MCP-Tool] Timeout running: {command[0]}")
        return "", "timeout", 1
    except Exception as e:
        print(f"[MCP-Tool] Error running {command[0]}: {e}")
        return "", str(e), 1


def _which(tool: str) -> Optional[str]:
    """Find tool in PATH, return None if not found."""
    return shutil.which(tool)


# ---------------------------------------------------------------------------
# Maigret Wrapper — 3000+ sites username search
# ---------------------------------------------------------------------------

class MaigretWrapper:
    """
    Maigret: Advanced username reconnaissance across 3000+ sites.
    Includes false-positive filtering and confidence scoring.
    Install: pip install maigret
    """

    async def investigate(
        self, username: str, timeout: int = 90
    ) -> List[OSINTFinding]:
        findings = []
        maigret_bin = _which("maigret")
        if not maigret_bin:
            print("[Maigret] Not installed or not in PATH. Skipping.")
            return findings

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                maigret_bin, username,
                "--timeout", "5",
                "--json", "simple",
                "-o", os.path.join(tmpdir, f"{username}.json")
            ]
            stdout, stderr, rc = await _run_tool(cmd, timeout=timeout)

            # Try to parse JSON output file
            json_out = Path(tmpdir) / f"{username}.json"
            if json_out.exists():
                try:
                    data = json.loads(json_out.read_text(encoding="utf-8"))
                    sites = data.get("sites", data) if isinstance(data, dict) else {}
                    if isinstance(sites, dict):
                        for site_name, info in sites.items():
                            if isinstance(info, dict) and info.get("status") == "Claimed":
                                findings.append(OSINTFinding(
                                    source="maigret",
                                    entity_type="username",
                                    entity_value=username,
                                    platform=site_name,
                                    url=info.get("url_user", ""),
                                    confidence=0.88,
                                    metadata={"tags": info.get("tags", [])}
                                ))
                except Exception as e:
                    print(f"[Maigret] JSON parse error: {e}")

            # Fallback: parse stdout
            if not findings and stdout:
                for line in stdout.splitlines():
                    if "[+]" in line or "Found" in line.lower():
                        url_match = re.search(r"https?://\S+", line)
                        site_match = re.search(r"\[([^\]]+)\]", line)
                        findings.append(OSINTFinding(
                            source="maigret",
                            entity_type="username",
                            entity_value=username,
                            platform=site_match.group(1) if site_match else "Unknown",
                            url=url_match.group(0) if url_match else "",
                            confidence=0.80
                        ))

        print(f"[Maigret] Found {len(findings)} accounts for '{username}'")
        return findings


# ---------------------------------------------------------------------------
# Blackbird Wrapper — fast multi-platform username search
# ---------------------------------------------------------------------------

class BlackbirdWrapper:
    """
    Blackbird: Lightning-fast username OSINT across 581 sites.
    Complements Sherlock with different site coverage.
    Install: git clone https://github.com/p1ngul1n0/blackbird
    """

    def __init__(self):
        self.script_path = (
            os.environ.get("BLACKBIRD_PATH")
            or "blackbird.py"
        )

    async def investigate(
        self, username: str, timeout: int = 60
    ) -> List[OSINTFinding]:
        findings = []

        # Try installed binary first
        blackbird_bin = _which("blackbird")
        if blackbird_bin:
            cmd = [blackbird_bin, "-u", username]
        elif Path(self.script_path).exists():
            cmd = [sys.executable, self.script_path, "-u", username, "--json"]
        else:
            print("[Blackbird] Not installed. Skipping.")
            return findings

        with tempfile.TemporaryDirectory() as tmpdir:
            out_json = Path(tmpdir) / f"{username}.json"
            cmd_with_out = cmd + ["--json", str(out_json)]
            stdout, stderr, rc = await _run_tool(cmd_with_out, timeout=timeout)

            if out_json.exists():
                try:
                    data = json.loads(out_json.read_text(encoding="utf-8"))
                    for site in data.get("found", data if isinstance(data, list) else []):
                        if isinstance(site, dict):
                            findings.append(OSINTFinding(
                                source="blackbird",
                                entity_type="username",
                                entity_value=username,
                                platform=site.get("name", site.get("site", "Unknown")),
                                url=site.get("url", ""),
                                confidence=0.82
                            ))
                except Exception as e:
                    print(f"[Blackbird] JSON parse error: {e}")

            # Fallback stdout parse
            if not findings:
                for line in stdout.splitlines():
                    if "[+]" in line or "FOUND" in line.upper():
                        url_match = re.search(r"https?://\S+", line)
                        findings.append(OSINTFinding(
                            source="blackbird",
                            entity_type="username",
                            entity_value=username,
                            platform="Social",
                            url=url_match.group(0) if url_match else "",
                            confidence=0.75
                        ))

        print(f"[Blackbird] Found {len(findings)} accounts for '{username}'")
        return findings


# ---------------------------------------------------------------------------
# GHunt Wrapper — Google account intelligence
# ---------------------------------------------------------------------------

class GHuntWrapper:
    """
    GHunt: Extract Google account info from Gmail or Google ID.
    Reveals Google Maps reviews, YouTube activity, Calendar, etc.
    Install: pip install ghunt  (requires OAuth setup)
    """

    async def investigate(
        self, identifier: str, timeout: int = 60
    ) -> List[OSINTFinding]:
        findings = []
        ghunt_bin = _which("ghunt")
        if not ghunt_bin:
            print("[GHunt] Not installed or not in PATH. Skipping.")
            return findings

        cmd = [ghunt_bin, "email", identifier]
        stdout, stderr, rc = await _run_tool(cmd, timeout=timeout)

        if rc == 0 and stdout:
            # Parse key fields from GHunt output
            name_match = re.search(r"Name:\s*(.+)", stdout)
            gaia_match = re.search(r"Gaia ID:\s*(\d+)", stdout)
            photo_match = re.search(r"Profile picture:\s*(https?://\S+)", stdout)

            meta: Dict[str, Any] = {}
            if name_match:
                meta["google_name"] = name_match.group(1).strip()
            if gaia_match:
                meta["gaia_id"] = gaia_match.group(1).strip()
            if photo_match:
                meta["profile_photo"] = photo_match.group(1).strip()

            # Extract any YouTube channel
            yt_match = re.search(r"(https?://www\.youtube\.com/channel/[^\s]+)", stdout)
            if yt_match:
                meta["youtube_channel"] = yt_match.group(1)

            findings.append(OSINTFinding(
                source="ghunt",
                entity_type="email",
                entity_value=identifier,
                platform="Google",
                confidence=0.92 if name_match else 0.70,
                metadata=meta
            ))

        print(f"[GHunt] {'Found' if findings else 'No'} Google account data for '{identifier}'")
        return findings


# ---------------------------------------------------------------------------
# SpiderFoot Wrapper — comprehensive OSINT scan
# ---------------------------------------------------------------------------

class SpiderFootWrapper:
    """
    SpiderFoot: The Swiss Army knife of OSINT.
    Performs 200+ module deep-scan. Can take 5-30 minutes.
    Install: git clone https://github.com/smicallef/spiderfoot
    WARNING: Only use for formal investigations, NOT casual queries.
    """

    def __init__(self):
        self.sf_path = (
            os.environ.get("SPIDERFOOT_PATH", "")
            or ("/opt/spiderfoot/sf.py" if sys.platform != "win32"
                else _which("sf.py") or "sf.py")
        )

    async def investigate(
        self, target: str, timeout: int = 1800  # 30 min max
    ) -> List[OSINTFinding]:
        findings = []

        if not Path(self.sf_path).exists() and not _which("sf.py"):
            print("[SpiderFoot] Not installed. Skipping.")
            return findings

        cmd_path = self.sf_path if Path(self.sf_path).exists() else "sf.py"
        cmd = [sys.executable, cmd_path, "-s", target, "-u", "all", "-o", "json", "-q"]
        stdout, stderr, rc = await _run_tool(cmd, timeout=timeout)

        if rc == 0 and stdout:
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    for item in data:
                        findings.append(OSINTFinding(
                            source="spiderfoot",
                            entity_type=item.get("type", "unknown").lower(),
                            entity_value=item.get("data", ""),
                            platform=item.get("module", "spiderfoot"),
                            confidence=0.75,
                            metadata={
                                "source_module": item.get("module", ""),
                                "risk": item.get("risk", "INFO"),
                            }
                        ))
            except json.JSONDecodeError:
                # Parse raw text output
                for line in stdout.splitlines():
                    if line.strip():
                        findings.append(OSINTFinding(
                            source="spiderfoot",
                            entity_type="raw",
                            entity_value=line.strip(),
                            platform="spiderfoot",
                            confidence=0.60
                        ))

        print(f"[SpiderFoot] Found {len(findings)} records for '{target}'")
        return findings


# ---------------------------------------------------------------------------
# Aggregated MCP Tool Runner
# ---------------------------------------------------------------------------

class MCPToolsOrchestrator:
    """
    Orchestrates all MCP-derived OSINT tools in parallel.
    Returns merged OSINTFinding list with deduplication.
    """

    def __init__(self):
        self.maigret = MaigretWrapper()
        # SpiderFoot is opt-in (slow), instantiate lazily
        self._spiderfoot: Optional[SpiderFootWrapper] = None

    @property
    def spiderfoot(self) -> SpiderFootWrapper:
        if self._spiderfoot is None:
            self._spiderfoot = SpiderFootWrapper()
        return self._spiderfoot

    async def run_for_username(
        self, username: str, use_spiderfoot: bool = False
    ) -> List[OSINTFinding]:
        """Run all username-oriented tools concurrently."""
        print(f"[MCPOrchestrator] Running username tools for: {username}")
        tasks = [
            self.maigret.investigate(username),
        ]
        if use_spiderfoot:
            tasks.append(self.spiderfoot.investigate(username))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return _flatten_results(results)

    async def run_for_email(
        self, email: str, use_ghunt: bool = True, use_spiderfoot: bool = False
    ) -> List[OSINTFinding]:
        """Run all email-oriented tools concurrently."""
        print(f"[MCPOrchestrator] Running email tools for: {email}")
        tasks = []
        if use_spiderfoot:
            tasks.append(self.spiderfoot.investigate(email))

        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return _flatten_results(results)

    async def run_for_domain(
        self, domain: str, use_spiderfoot: bool = False
    ) -> List[OSINTFinding]:
        """Run domain-focused tools."""
        print(f"[MCPOrchestrator] Running domain tools for: {domain}")
        tasks = []
        if use_spiderfoot:
            tasks.append(self.spiderfoot.investigate(domain))
        
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return _flatten_results(results)

    async def run_for_target(
        self,
        target_type: str,
        target_value: str,
        use_spiderfoot: bool = False
    ) -> List[OSINTFinding]:
        """Dispatch to the right set of tools based on target type."""
        if target_type == "username":
            return await self.run_for_username(target_value, use_spiderfoot)
        elif target_type == "email":
            return await self.run_for_email(target_value, use_spiderfoot=use_spiderfoot)
        elif target_type == "domain":
            return await self.run_for_domain(target_value, use_spiderfoot)
        elif target_type in ("name", "phone", "ip"):
            # SpiderFoot is best for these
            if use_spiderfoot:
                return await self.spiderfoot.investigate(target_value)
            return []
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten_results(results) -> List[OSINTFinding]:
    """Flatten gather() results, skip exceptions, deduplicate by (source, url)."""
    seen = set()
    flat = []
    for res in results:
        if isinstance(res, Exception):
            print(f"[MCPOrchestrator] Tool error: {res}")
            continue
        if isinstance(res, list):
            for f in res:
                key = (f.source, f.url or f.entity_value)
                if key not in seen:
                    seen.add(key)
                    flat.append(f)
    return flat
