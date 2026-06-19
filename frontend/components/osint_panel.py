"""
OSINT investigation panel
"""
import streamlit as st
import pandas as pd
import json
import urllib.parse
from typing import Dict, Optional

from frontend.utils.api_client import api_client

PLATFORM_ICONS = {
    'Instagram': 'IG', 'LinkedIn': 'LI', 'GitHub': 'GH', 'Twitter/X': 'TW',
    'Facebook': 'FB', 'YouTube': 'YT', 'TikTok': 'TK', 'Reddit': 'RD',
    'Stack Overflow': 'SO', 'GitLab': 'GL', 'Quora': 'QR', 'Medium': 'MD',
}

CATEGORY_ICON = {
    'social': '[S]', 'professional': '[P]', 'dev': '[D]', 'news_context': '[N]',
    'breaches': '[!]', 'documents': '[F]', 'academic': '[A]', 'government': '[G]',
    'identity': '[I]', 'institution_site': '[C]', 'broad_recon': '[R]',
    'internal': '[INT]',
}


def render_osint_panel():
    """Render OSINT investigation interface"""
    st.header("OSINT Investigation")

    case = st.session_state.get("investigation_case")
    is_quick_search = not case

    if not case:
        st.info("No case selected — running in Quick Search mode. Results will not be saved.")
    else:
        st.info(f"Case: **{case['case_number']}** — {case['title']}")
        if st.button("Clear Case / Quick Search"):
            st.session_state.investigation_case = None
            st.rerun()

    # --- Search form ---
    # Check for pre-fill values injected by Case Manager
    prefill_target = st.session_state.pop("osint_prefill_target", "")
    prefill_type = st.session_state.pop("osint_prefill_type", "Auto-Detect")

    with st.form("osint_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            target = st.text_input(
                "Target",
                value=prefill_target,
                placeholder="Name, username, email, phone, UPI ID, domain, or IP"
            )
        with col2:
            type_options = ["Auto-Detect", "Name", "Organization", "Username", "Email", "Phone",
                            "UPI ID", "Domain", "IP Address", "Bank Account"]
            type_index = type_options.index(prefill_type) if prefill_type in type_options else 0
            target_type = st.selectbox(
                "Type",
                type_options,
                index=type_index
            )
            
            llm_model = st.selectbox(
                "AI Model",
                ["qwen2.5:0.5b", "qwen3.5:4b", "llama3.1:latest"],
                index=0
            )

        # Context fields — critical for pinpointing individuals
        col3, col4 = st.columns(2)
        with col3:
            institution = st.text_input(
                "Institution / Organization (optional)",
                placeholder="e.g. Marian Engineering College, TCS, IIT Bombay"
            )
        with col4:
            location = st.text_input(
                "Location hint (optional)",
                placeholder="e.g. Kerala, Mumbai, India"
            )

        submitted = st.form_submit_button(
            "Quick Search" if is_quick_search else "Investigate (Save to Case)",
            type="primary", use_container_width=True
        )

    if submitted and target:
        _run_investigation(
            case.get("id") if case else None,
            target_type, target, institution, location, is_quick_search, llm_model
        )

    if case:
        st.markdown("---")
        col_h1, col_h2 = st.columns([4, 1])
        with col_h1:
            st.subheader("Job History")
        with col_h2:
            if st.button("🔄 Refresh Jobs", use_container_width=True):
                st.rerun()
        
        jobs_res = api_client.get(f"/api/v1/cases/{case['id']}/jobs")
        if isinstance(jobs_res, list) and len(jobs_res) > 0:
            for job in sorted(jobs_res, key=lambda x: x.get("created_at", ""), reverse=True):
                col_j1, col_j2, col_j3 = st.columns([3, 2, 2])
                with col_j1:
                    st.write(f"**Target:** {job.get('target_value')} ({job.get('job_type')})")
                with col_j2:
                    status_col = {"completed": "🟢", "running": "🟡", "failed": "🔴", "pending": "⚪"}.get(job.get("status"), "⚪")
                    st.write(f"**Status:** {status_col} {job.get('status', '').upper()}")
                with col_j3:
                    if job.get("status") == "completed":
                        if st.button("View Results", key=f"view_{job['id']}", use_container_width=True):
                            st.session_state.last_investigation = job.get("result_data")
                            st.rerun()
                    elif job.get("status") in ["running", "pending"]:
                        st.caption("Running...")
            st.markdown("---")
        else:
            st.info("No previous OSINT jobs for this case.")

    if st.session_state.get("last_investigation"):
        _render_results(st.session_state.last_investigation)


def _run_investigation(
    case_id: Optional[str], target_type: str, target: str,
    institution: str, location: str, is_quick_search: bool, llm_model: str
):
    with st.spinner("Running OSINT investigation... this may take 30-90 seconds"):
        progress = st.progress(0)

        # Auto-detect type
        api_type = target_type.lower()
        if api_type == "auto-detect":
            import re
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", target):
                api_type = "ip"
            elif "@" in target:
                api_type = "email" if "." in target.split("@")[1] else "upi"
            elif re.match(r"^\+?[6-9]\d{9}$", target):
                api_type = "phone"
            elif "." in target and " " not in target:
                api_type = "domain"
            elif " " in target.strip():
                api_type = "name"
            else:
                api_type = "username"
            st.info(f"Auto-detected type: **{api_type.capitalize()}**")
        else:
            api_type = target_type.lower().replace(" ", "_")

        progress.progress(15)

        if is_quick_search:
            params = (
                f"target_type={api_type}"
                f"&target_value={urllib.parse.quote(target, safe='')}"
                f"&institution={urllib.parse.quote(institution, safe='')}"
                f"&location={urllib.parse.quote(location, safe='')}"
                f"&llm_model={urllib.parse.quote(llm_model, safe='')}"
            )
            result = api_client.post(
                f"/api/v1/osint/quick-search?{params}", {},
                timeout=600
            )
            progress.progress(100)

            if "error" in result:
                err = result.get("error", "")
                if err == "connection_error":
                    st.error("Backend API not reachable. Start the server: `uvicorn backend.api.main:app --reload`")
                elif err == "timeout":
                    st.error("Search timed out. Try a more specific target or add institution context.")
                else:
                    st.error(f"Search failed: {result.get('detail', err)}")
                return

            st.session_state.last_investigation = result
            n = len(result.get("source_links", []))
            st.success(f"Done. Found {n} sources.")
        else:
            result = api_client.post("/api/v1/osint/investigate", {
                "case_id": case_id, "target_type": api_type,
                "target_value": target, "priority": 3, "llm_model": llm_model
            }, timeout=600)
            if "error" in result:
                st.error(f"Investigation failed: {result.get('detail', result.get('error'))}")
                return
            job_id = result.get("id")
            import time
            for i in range(100):
                time.sleep(0.1)
                progress.progress(i + 1)
            job_result = api_client.get(f"/api/v1/osint/jobs/{job_id}")
            if "error" not in job_result and job_result.get("result_data"):
                st.session_state.last_investigation = job_result["result_data"]
                st.success("Investigation complete.")
            else:
                st.warning("Job submitted. Results will appear when ready.")


def _render_results(results: Dict):
    """Render investigation results"""
    st.markdown("---")

    meta = results.get("metadata", {})
    target_value = meta.get("target_value") or results.get("target_value", "")
    target_type = meta.get("target_type") or results.get("target_type", "")
    institution = meta.get("institution", "")
    location = meta.get("location", "")
    proc_time = meta.get("processing_time")
    source_links = results.get("source_links", [])
    github_profiles = results.get("github_profiles", [])

    # --- Summary bar ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Target", (target_value[:22] + "...") if len(target_value) > 22 else target_value)
    c2.metric("Type", target_type.upper())
    c3.metric("Sources Found", len(source_links))
    if proc_time:
        c4.metric("Scan Time", f"{proc_time:.1f}s")

    if institution:
        st.caption(f"Context: {institution}" + (f" | {location}" if location else ""))

    # --- Platform presence badges ---
    platforms_found = list(dict.fromkeys(
        sl.get("platform", "") for sl in source_links if sl.get("platform")
    ))
    if platforms_found:
        st.markdown("**Platform presence:** " + "  ".join(
            f"`{p}`" for p in platforms_found
        ))

    # --- GitHub profile card ---
    if github_profiles:
        with st.expander(f"GitHub Profiles Found ({len(github_profiles)})", expanded=True):
            for gp in github_profiles:
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**[{gp['login']}]({gp['profile_url']})**" +
                                (f" — {gp['name']}" if gp.get('name') else ""))
                    if gp.get('avatar_url'):
                        st.image(gp['avatar_url'], width=80)
                    if gp.get('bio'):
                        st.caption(f"Bio: {gp['bio']}")
                    details = []
                    if gp.get('location'): details.append(f"Location: {gp['location']}")
                    if gp.get('company'): details.append(f"Company: {gp['company']}")
                    if gp.get('email'): details.append(f"Email: {gp['email']}")
                    if gp.get('blog'): details.append(f"Blog: {gp['blog']}")
                    if gp.get('created_at'): details.append(f"Joined: {gp['created_at'][:10]}")
                    if details:
                        st.caption(" | ".join(details))
                with col_b:
                    st.metric("Followers", gp.get('followers', 0))
                    st.metric("Repos", gp.get('public_repos', 0))
                st.divider()

    # --- Threat assessment ---
    threat = results.get("threat_assessment")
    if threat:
        level = threat.get("level", "LOW")
        score = threat.get("score", 0.0)
        color = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red", "CRITICAL": "red"}.get(level, "gray")
        st.markdown(f"**Threat Level: {level}** &nbsp; Risk Score: `{score:.2f}`")
        st.progress(min(score, 1.0))
        for ind in threat.get("indicators", []):
            st.warning(ind)
        st.markdown("---")

    # --- Opsec warnings ---
    for w in results.get("opsec_warnings", []):
        st.error(w)
    for s in results.get("recommended_next_steps", []):
        st.info(s)

    # --- Tabs ---
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🤖 AI Report & Profiles", "🔍 Extracted Entities",
        "📄 Source Evidence", "💻 GitHub", "🗃️ Raw JSON"
    ])

    with tab1:
        _render_llm_profile(results)
        
        st.markdown("### 🔗 Correlated Identities & Likelihoods")
        correlated = results.get("correlated_profiles", [])
        if correlated:
            for prof in correlated:
                pid = prof.get("profile_id", "")
                score = prof.get("confidence_score", 0)
                platform = prof.get("platform", "")
                profile_url = prof.get("profile_url", "")
                with st.expander(
                    f"{pid}  |  Confidence: {score:.0%}" +
                    (f"  |  {platform}" if platform else "")
                ):
                    if profile_url:
                        st.markdown(f"Profile: [{profile_url}]({profile_url})")
                    for j in prof.get("justifications", []):
                        st.markdown(f"- {j}")
                    for doc in prof.get("document_urls", []):
                        st.markdown(f"- Doc: [{doc}]({doc})")
                    handles = prof.get("handles", [])
                    if handles:
                        st.markdown(f"- Handles: `{'`, `'.join(handles)}`")
        else:
            st.info("No correlated profiles found.")

    with tab2:
        entities = results.get("extracted_entities", {})
        display = []
        for etype, vals in entities.items():
            if vals and isinstance(vals, list):
                for v in vals:
                    display.append({"Type": etype.replace("_", " ").title(), "Value": v})
        if display:
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.info("No entities extracted.")

    with tab3:
        _render_source_evidence(source_links)

    with tab4:
        if github_profiles:
            st.json(github_profiles)
        else:
            st.info("No GitHub API results.")

    with tab5:
        st.json(results)

    # --- Actions ---
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add to Graph Database", use_container_width=True):
            with st.spinner("Adding to graph database..."):
                try:
                    meta = results.get("metadata", {})
                    target_value = meta.get("target_value") or results.get("target_value", "")
                    target_type = meta.get("target_type") or results.get("target_type", "")
                    
                    # 1. Create central node
                    center_res = api_client.post("/api/v1/graph/entities", {
                        "type": "DigitalIdentity",
                        "properties": {
                            target_type: target_value,
                            "name": target_value,
                            "discovered_via": "osint_investigation_manual_add"
                        }
                    })
                    
                    if "error" in center_res:
                        st.error(f"Failed to add central entity: {center_res['error']}")
                    else:
                        center_id = center_res.get("id")
                        added_count = 0
                        
                        def map_node_type(etype: str) -> str:
                            if etype in ["name", "aliases"]: return "Person"
                            if etype in ["bank_account_id", "upi_id", "crypto_wallet"]: return "FinancialInstrument"
                            if etype in ["ip_address", "device_fingerprint"]: return "Device"
                            if etype in ["locations"]: return "Location"
                            if etype in ["affiliations", "institutions", "organization"]: return "Organization"
                            return "DigitalIdentity"

                        extracted = results.get("extracted_entities", {})
                        related_ids = []
                        for entity_type, values in extracted.items():
                            if not values or entity_type in ["modus_operandi", "active_hours", "key_findings", "roll_numbers", "flags"]:
                                continue
                            
                            for value in values:
                                if value == target_value:
                                    continue
                                
                                # Create node
                                node_type = map_node_type(entity_type)
                                node_res = api_client.post("/api/v1/graph/entities", {
                                    "type": node_type,
                                    "properties": {
                                        "type": entity_type,
                                        "value": value,
                                        "name": value
                                    }
                                })
                                
                                if "error" not in node_res and node_res.get("id"):
                                    related_id = node_res["id"]
                                    related_ids.append(related_id)
                                    # Create relationship
                                    api_client.post("/api/v1/graph/relationships", {
                                        "source_id": center_id,
                                        "target_id": related_id,
                                        "type": "HAS_IDENTIFIER",
                                        "properties": {"confidence": 0.8}
                                    })
                                    added_count += 1
                                    
                        # Create nodes for correlated profiles if they don't exist
                        correlated = results.get("correlated_profiles", [])
                        for prof in correlated:
                            pid = prof.get("profile_id", "")
                            platform = prof.get("platform", "")
                            if not pid or not platform:
                                continue
                            prof_res = api_client.post("/api/v1/graph/entities", {
                                "type": "DigitalIdentity",
                                "properties": {
                                    "type": "profile",
                                    "value": pid,
                                    "name": pid,
                                    "platform": platform
                                }
                            })
                            if "error" not in prof_res and prof_res.get("id"):
                                prof_id = prof_res["id"]
                                api_client.post("/api/v1/graph/relationships", {
                                    "source_id": center_id,
                                    "target_id": prof_id,
                                    "type": "RELATED_TO",
                                    "properties": {"confidence": prof.get("confidence_score", 0.5)}
                                })
                                added_count += 1
                        
                        st.success(f"Successfully added target and {added_count} related entities to graph database.")
                except Exception as e:
                    st.error(f"Error adding to graph: {e}")
    with col2:
        st.download_button(
            "Download Raw OSINT JSON",
            data=json.dumps(results, indent=2),
            file_name=f"osint_results.json",
            mime="application/json",
            use_container_width=True
        )


def _render_source_evidence(source_links: list):
    if not source_links:
        st.info("No source links. Backend may be offline or search returned no results.")
        return

    # Summary metrics
    categories = sorted(set(sl.get("category", "general") for sl in source_links))
    platforms = sorted(set(sl.get("platform", "") for sl in source_links if sl.get("platform")))
    scraped_count = sum(1 for sl in source_links if sl.get("scraped"))

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Sources", len(source_links))
    mc2.metric("Deep Scraped", scraped_count)
    mc3.metric("Platforms", len(platforms))

    # Category filter
    selected_cats = st.multiselect(
        "Filter by category",
        options=categories, default=categories,
        key="src_cat_filter"
    )

    filtered = [sl for sl in source_links if sl.get("category", "general") in selected_cats]

    for sl in filtered:
        cat = sl.get("category", "general")
        platform = sl.get("platform", "")
        icon = CATEGORY_ICON.get(cat, "[ ]")
        scraped_badge = " [scraped]" if sl.get("scraped") else ""
        title = sl.get("title", "Untitled")
        url = sl.get("url", "#")
        snippet = sl.get("snippet", "")
        pub_date = sl.get("published_date", "")
        author = sl.get("author", "")
        handle = sl.get("handle", "")
        engine = sl.get("engine", "")

        col_main, col_meta = st.columns([5, 1])
        with col_main:
            st.markdown(f"{icon} **[{title}]({url})**{scraped_badge}")
            if snippet:
                st.caption(f"{snippet[:260]}{'...' if len(snippet) > 260 else ''}")
            detail_parts = []
            if pub_date:
                detail_parts.append(f"Published: {pub_date[:10]}")
            if author:
                detail_parts.append(f"By: {author}")
            if handle:
                detail_parts.append(f"Handle: @{handle}")
            if detail_parts:
                st.caption(" | ".join(detail_parts))
        with col_meta:
            if platform:
                st.caption(f"`{platform}`")
            st.caption(f"`{cat}`")
            if engine:
                st.caption(f"{engine}")
        st.divider()


def _render_llm_profile(results: Dict):
    llm_data = results.get("llm_profile", {})
    if not llm_data:
        st.info("No AI behavioral profile generated. The LLM may have been disabled or failed to return valid JSON.")
        return

    st.markdown("### 🤖 Behavioral Analysis")
    findings = llm_data.get("key_findings", [])
    if findings:
        for f in findings:
            st.markdown(f"• {f}")
    else:
        st.write("Manual review of findings recommended.")
    
    behavioral = llm_data.get("behavioral_profile", {})
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Activity:** `{behavioral.get('activity', 'UNKNOWN')}`")
        st.markdown(f"**Footprint:** `{behavioral.get('footprint', 'UNKNOWN')}`")
    with col2:
        st.markdown(f"**Persona:** `{behavioral.get('persona', 'UNKNOWN')}`")
        st.markdown(f"**Confidence:** `{llm_data.get('identity_confidence', {}).get('score', 0):.2f}`")

    # Threat indicators as simple warnings
    for r in llm_data.get("threat_indicators", []):
        st.warning(f"⚠️ {r}")

    # Display recommended steps if present as simple text
    steps = llm_data.get("recommended_steps", [])
    if steps:
        st.markdown("---")
        for s in steps:
            st.markdown(f"📍 {s}")

    # Display which model generated this
    meta = results.get("metadata", {})
    llm_enabled = meta.get("llm_enabled", False)
    mcp_enabled = meta.get("ollama_mcp_enabled", False)
    
    st.markdown("---")
    st.caption(f"**Generation Details:**")
    st.caption(f"LLM Comprehension: `{'Enabled' if llm_enabled else 'Disabled'}` | Model: `{meta.get('llm_provider', 'none')}`")
    st.caption(f"Ollama-MCP Tools: `{'Enabled' if mcp_enabled else 'Disabled'}` | Model: `{meta.get('ollama_model', 'none')}`")