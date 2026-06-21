# OSINT-V1: Autonomous Cyber Profiling & Threat Intelligence Engine

OSINT-V1 is a state-of-the-art, multi-agent Open Source Intelligence (OSINT) framework designed for deep persona investigations, entity correlation, and threat intelligence. Powered by a local LLM integration (e.g., Llama 3.1 / Qwen 2.5 via Ollama) and a robust ReAct (Reasoning and Acting) autonomous agent loop, it cross-references usernames, emails, IP addresses, and other identifiers across the clear web, social media, breach databases, and public records.

> **Note**: For an in-depth dive into the architecture, agent workflows, and API specifications, please refer to our [Detailed Documentation](DOCUMENTATION.md).

## Key Features

- **Multi-Agent ReAct Workflow**: Operates using autonomous agents (Manager, Scraper, Correlation, Tool Discovery) that iteratively plan, execute tools, scrape footprints, and synthesize findings without human intervention.
- **Advanced Tor Circuit Rotation**: Built-in anonymity and rate-limit bypassing. Detects 429/403 blocks from search engines (like DuckDuckGo) and automatically commands the Tor daemon to burn its identity and rotate circuits (IP addresses) on the fly.
- **Deep Web Scraping**: Utilizes `curl_cffi` for lightweight TLS-impersonation to bypass Cloudflare, with an automatic fallback to headless Chromium (`patchright`) for complex, JavaScript-rendered websites.
- **Resilient AI Parsing**: Employs `json-repair` to dynamically reconstruct and fix structurally damaged JSON payloads output by smaller local LLMs, ensuring uninterrupted pipeline execution.
- **Interactive UI**: A beautiful, glassmorphic Streamlit dashboard for real-time visualization of agent thoughts, terminal logs, confidence scoring, and Markdown-rendered target summaries.
- **Case Management & Dossier Generation**: Organize investigations into distinct cases and automatically generate comprehensive Markdown dossiers summarizing agent findings and gathered intelligence.
- **Advanced Network Visualization**: Interactive master graph expansion, automated criminal syndicate detection, and shortest-path finding between targets and entities.

---

## Prerequisites

1. **Python 3.10+** (Tested on Python 3.13)
2. **Ollama**: Installed locally with your preferred models (e.g., `llama3.1:latest` or `qwen2.5:0.5b`).
3. **Tor Service**: 
   - **CRITICAL REQUIREMENT**: The OSINT engine routes traffic through the Tor network to preserve anonymity and bypass strict OSINT rate-limits.
   - You MUST have the Tor service running locally.
   - Default Configuration expects Tor SOCKS5 on `127.0.0.1:9050` and the Tor Control Port on `127.0.0.1:9051`.
   - Ensure you have a Tor password set up or cookie authentication enabled so the `stem` library can issue the `NEWNYM` signal for IP rotation.
4. **Git** and OSINT CLI binaries (like Sherlock, Holehe) accessible in your environment.

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/abhinavmanoj05/OSINT-V1.git
   cd OSINT-V1
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: The dependencies include heavy ML and browser instrumentation libraries like `patchright`, `langgraph`, `duckduckgo-search` (ddgs), and `streamlit`)*

4. **Install Playwright/Patchright Browsers:**
   ```bash
   patchright install chromium
   ```

5. **Run the Setup Wizard:**
   To automatically configure your `.env` file, select your Ollama model, and configure your Tor executable path, run:
   ```bash
   python setup.py
   ```

---

## How to Use

1. **Start Ollama** locally and ensure your model is pulled:
   ```bash
   ollama pull llama3.1
   ```

2. **Launch the Application**:
   Use the master runner script which automatically launches the FastAPI Backend, Streamlit Frontend, Celery worker, and Tor background service:
   ```bash
   python run.py
   ```
   *The UI will be automatically available at `http://localhost:8501`*

4. **Run a Quick Search**:
   - Navigate to the Streamlit UI in your browser.
   - Select a Target Type (e.g., `Username`).
   - Enter the Target Value (e.g., `DeveloperAromal`).
   - Click "Search".
   - The UI will stream live agent thoughts and terminal logs as it rotates Tor IPs, queries DuckDuckGo, scrapes repositories, and correlates a final profile markdown report!

---

## Adding Additional Tools to the Agent Workflow

The ReAct Agent loop is highly extensible. If you want to integrate new OSINT tools (like Shodan, HaveIBeenPwned, or custom internal API scrapers), you can easily add them to the `agent_workflow`:

1. **Create the Tool Module**: 
   Inside `agent_workflow/tools/`, create a new `.py` file (e.g., `shodan_tool.py`).
2. **Define the LangChain BaseTool**:
   ```python
   from pydantic import BaseModel, Field
   from langchain_core.tools import BaseTool
   
   class ShodanInput(BaseModel):
       ip_address: str = Field(...)
       
   class ShodanSearchTool(BaseTool):
       name: str = "shodan_ip_lookup"
       description: str = "Use this to lookup open ports and vulnerabilities for an IP."
       args_schema: type[BaseModel] = ShodanInput
       
       def _run(self, ip_address: str, **kwargs):
           # Implement your lookup logic here (remember to route via Tor if necessary!)
           return raw_data
   ```
3. **Register the Tool**:
   Import and append your tool to the master `TOOLS` list inside `agent_workflow/react_agent.py` or the specific discovery agent manifest. The LLM will automatically read the tool's `description` and decide when to use it autonomously!

---

## Disclaimer

This engine is built for **educational, defensive cybersecurity, and authorized threat-hunting purposes only**. Do not use this framework to investigate individuals or infrastructure without explicit consent or legal authorization. The inclusion of Tor routing is intended to prevent tracking and IP bans during authorized high-volume scanning, not to obscure malicious activity.
