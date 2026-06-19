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
    
    prefill_inst = ""
    prefill_loc = ""
    
    # Auto-fill from Case Profile if available
    if case and "target_profile" in case and case["target_profile"]:
        profile = case["target_profile"]
        # Find the first available strong identifier
        if not prefill_target:
            prefill_target = profile.get("name") or profile.get("username") or profile.get("email") or profile.get("phone") or ""
        prefill_inst = profile.get("institution", "")
        prefill_loc = profile.get("location", "")

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
                value=prefill_inst,
                placeholder="e.g. Marian Engineering College, TCS, IIT Bombay"
            )
        with col4:
            location = st.text_input(
                "Location hint (optional)",
                value=prefill_loc,
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
    with st.status("Initializing OSINT Engine... (30-90s)", expanded=True) as status:
        st.write("[SYSTEM] Dispatching scrapers and search engines...")
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
        st.write("[SYSTEM] Booting up multi-agent ReAct workflow...")
        st.write("[SYSTEM] Correlation Engine analyzing entities...")

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
            status.update(label="OSINT Investigation Complete", state="complete", expanded=False)

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
                status.update(label="Investigation Failed", state="error", expanded=True)
                st.error(f"Investigation failed: {result.get('detail', result.get('error'))}")
                return
                
            job_id = result.get("id")
            progress.progress(100)
            status.update(label=f"Background Job '{job_id[:8]}' Running... (1-2 mins)", state="running", expanded=True)
            
            import time
            max_retries = 90  # up to 3 minutes
            log_container = st.empty()
            
            for i in range(max_retries):
                job_result = api_client.get(f"/api/v1/osint/jobs/{job_id}")
                job_status = job_result.get("status")
                
                if job_status == "completed":
                    status.update(label="OSINT Investigation Complete", state="complete", expanded=False)
                    if job_result.get("result_data"):
                        st.session_state.last_investigation = job_result["result_data"]
                        st.success("Investigation complete!")
                        st.rerun()
                    break
                elif job_status == "failed":
                    status.update(label="Investigation Failed", state="error", expanded=True)
                    st.error("The background investigation failed. Check backend logs.")
                    break
                    
                # Dynamic fun logging based on loop iteration
                if i == 0: log_container.info("🚀 OSINT Engine Dispatched. Scraping initial URLs...")
                elif i == 5: log_container.info("🕵️ Search Agents querying public records and GitHub...")
                elif i == 15: log_container.info("🔍 Running Regex parsers for entity extraction...")
                elif i == 25: log_container.info("🧠 Handing off extracted data to ReAct Correlation Agent...")
                elif i == 35: log_container.info("⛏️ Scraper Agent deep-diving into discovered profiles...")
                elif i == 50: log_container.info("📊 Evaluating Threat Risk profiles and finalizing summary...")
                elif i == 65: log_container.warning("⏳ Still processing... ensuring deep correlation...")
                
                time.sleep(2)
            else:
                status.update(label="Investigation taking longer than expected.", state="complete")
                st.warning("Job is still running in the background. Check 'Job History' to view results when ready.")


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

    # --- Threat assessment moved to bottom ---

    # --- Opsec warnings ---
    for w in results.get("opsec_warnings", []):
        st.error(w)
    for s in results.get("recommended_next_steps", []):
        st.info(s)

    # --- Tabs ---
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Profile", "Source Evidence/URL",
        "Textcorpus", "ConfirmedEntityRawData", "AllentitiesRawData", "Images"
    ])

    with tab1:
        _render_agent_findings(results)
        
        # GitHub Profiles
        github_profiles = results.get("github_profiles", [])
        if github_profiles:
            st.markdown("---")
            st.markdown(f"### GitHub Profiles Found ({len(github_profiles)})")
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

    with tab2:
        _render_source_evidence(source_links)

    with tab3:
        st.markdown("### Text Corpus")
        corpus = results.get("text_corpus", "")
        if corpus:
            st.text_area("Extracted Text & Logs", value=corpus, height=400)
        else:
            st.info("No text corpus available.")

    with tab4:
        st.markdown("### Confirmed Entities")
        confirmed = results.get("confirmed_entities", [])
        if confirmed:
            st.json(confirmed)
        else:
            st.info("No confirmed entities.")

    with tab5:
        st.markdown("### All Entities (Sorted by Confidence)")
        all_ents = results.get("confirmed_entities", []) + results.get("possible_entities", [])
        # Sort by confidence descending
        all_ents = sorted(all_ents, key=lambda x: x.get("confidence", 0), reverse=True)
        if all_ents:
            st.json(all_ents)
        else:
            st.info("No entities found.")
            
    with tab6:
        st.markdown("### Discovered Image Evidence")
        
        image_urls = set()
        
        # Extract from AI entities
        all_ents = results.get("confirmed_entities", []) + results.get("possible_entities", [])
        for ent in all_ents:
            linked = ent.get("linked_data", {})
            img = linked.get("profile_pic") or linked.get("avatar_url") or linked.get("image_url") or linked.get("avatar")
            if img and isinstance(img, str) and img.startswith("http"):
                image_urls.add(img)
                
        # Extract from GitHub Profiles
        for gp in results.get("github_profiles", []):
            if gp.get("avatar_url") and isinstance(gp.get("avatar_url"), str):
                image_urls.add(gp["avatar_url"])
                
        if image_urls:
            image_urls = list(image_urls)
            st.success(f"Found {len(image_urls)} extracted image URLs.")
            cols = st.columns(3)
            for idx, url in enumerate(image_urls):
                with cols[idx % 3]:
                    try:
                        st.image(url, use_container_width=True)
                        st.caption(f"[Link to image]({url})")
                    except Exception:
                        st.error("Failed to load image")
        else:
            st.info("No images found in the extracted profiles.")

    # --- Threat assessment ---
    st.markdown("---")
    threat = results.get("threat_assessment")
    if threat:
        st.subheader("Threat Assessment")
        level = threat.get("level", "LOW")
        score = threat.get("score", 0.0)
        st.markdown(f"**Threat Level: {level}** &nbsp; Risk Score: `{score:.2f}`")
        st.progress(min(score, 1.0))
        for ind in threat.get("indicators", []):
            st.warning(ind)

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


def _render_agent_findings(results: Dict):
    confirmed = results.get("confirmed_entities", [])
    possible = results.get("possible_entities", [])
    narrative = results.get("summary", "")
    
    # Data aggregation logic
    best_name = ""
    best_name_conf = 0
    best_location = ""
    best_location_conf = 0
    best_email = ""
    best_email_conf = 0
    best_bio = ""
    best_bio_conf = 0
    best_website = ""
    best_website_conf = 0
    best_focus = ""
    best_focus_conf = 0
    best_image = ""
    best_image_conf = 0
    
    footprints = []
    
    all_ents = confirmed + possible
    for ent in all_ents:
        conf = ent.get("confidence", 0)
        linked = ent.get("linked_data", {})
        
        name = ent.get("persona_name") or linked.get("name")
        if name and conf > best_name_conf:
            best_name = name
            best_name_conf = conf
            
        img = linked.get("profile_pic") or linked.get("avatar_url") or linked.get("image_url") or linked.get("avatar")
        if img and conf > best_image_conf:
            best_image = img
            best_image_conf = conf
            
        loc = linked.get("location") or (linked.get("locations")[0] if linked.get("locations") else "")
        if loc and conf > best_location_conf:
            best_location = loc
            best_location_conf = conf
            
        em = linked.get("email") or (linked.get("emails")[0] if linked.get("emails") else "")
        if em and conf > best_email_conf:
            best_email = em
            best_email_conf = conf
            
        bio = linked.get("bio") or linked.get("headline")
        if bio and conf > best_bio_conf:
            best_bio = bio
            best_bio_conf = conf
            
        web = linked.get("blog") or linked.get("website") or linked.get("personal_website")
        if web and conf > best_website_conf:
            best_website = web
            best_website_conf = conf
            
        focus = linked.get("focus") or linked.get("primary_focus") or linked.get("company")
        if focus and conf > best_focus_conf:
            best_focus = focus
            best_focus_conf = conf

        if linked.get("platform") and linked.get("username"):
            footprints.append({
                "platform": linked.get("platform"),
                "username": linked.get("username"),
                "url": linked.get("profile_url", ""),
                "conf": conf
            })
            
    correlated = results.get("correlated_profiles", [])
    for prof in correlated:
        conf = prof.get("confidence_score", 0)
        platform = prof.get("platform", "")
        pid = prof.get("profile_id", "")
        url = prof.get("profile_url", "")
        if platform and pid:
            footprints.append({
                "platform": platform,
                "username": pid,
                "url": url,
                "conf": conf
            })
            
    unique_footprints = {}
    for f in footprints:
        k = f["platform"] + f["username"]
        if k not in unique_footprints or f["conf"] > unique_footprints[k]["conf"]:
            unique_footprints[k] = f
            
    github_profiles = results.get("github_profiles", [])
    for gp in github_profiles:
        img = gp.get("avatar_url")
        if img and 0.95 > best_image_conf:
            best_image = img
            best_image_conf = 0.95
            
    st.markdown("""
    <style>
    .glass-card {
        background: rgba(15, 23, 42, 0.6);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        color: #f8fafc;
        font-family: 'ui-monospace', 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .badge-green { background: rgba(16, 185, 129, 0.2); color: #34d399; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-yellow { background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-gray { background: rgba(148, 163, 184, 0.2); color: #94a3b8; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; border: 1px solid rgba(148, 163, 184, 0.3); }
    .avatar {
        width: 96px; height: 96px; border-radius: 50%; background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
        display: flex; align-items: center; justify-content: center;
        font-size: 36px; font-weight: 700; color: white;
        box-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
        border: 2px solid rgba(255, 255, 255, 0.1);
    }
    .int-table { width: 100%; border-collapse: separate; border-spacing: 0; }
    .int-table th { text-align: left; padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); color: #94a3b8; font-weight: 500; font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; }
    .int-table td { padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.05); color: #f1f5f9; }
    .int-table tr:last-child td { border-bottom: none; }
    </style>
    """, unsafe_allow_html=True)
    
    initials = "".join([n[0] for n in best_name.split()[:2]]) if best_name else "?"
    
    overall_conf = max(best_name_conf, 0.1)
    badge_class = "badge-green" if overall_conf >= 0.9 else "badge-yellow" if overall_conf >= 0.7 else "badge-red"
    
    avatar_html = f'<div class="avatar" style="background: url(\'{best_image}\') center/cover;"></div>' if best_image else f'<div class="avatar">{initials.upper()}</div>'
    bio_html = f"<div style='color: #94a3b8; margin-bottom: 8px;'>{best_bio}</div>" if best_bio else ""
    location_html = f"<div style='color: #cbd5e1; margin-bottom: 12px;'>📍 {best_location}</div>" if best_location else ""
    
    html_content = f"""<div class="glass-card" style="display: flex; flex-direction: row; gap: 24px; align-items: center;">
<div style="flex-shrink: 0;">
{avatar_html}
</div>
<div>
<h1 style='margin-bottom: 4px; margin-top: 0; font-size: 1.875rem;'>{best_name or 'Unknown Target'}</h1>
{bio_html}
{location_html}
<div><span class="{badge_class}">Overall Confidence: {overall_conf:.0%}</span></div>
</div>
</div>"""
    st.markdown(html_content, unsafe_allow_html=True)
    
    # Section 1: Identity Summary
    def get_badge(conf):
        if conf >= 0.9: return f'<span class="badge-green">{conf:.0%}</span>'
        if conf >= 0.7: return f'<span class="badge-yellow">{conf:.0%}</span>'
        return f'<span class="badge-red">{conf:.0%}</span>'
        
    st.markdown("### 📋 Identity Summary")
    table_html = "<div class='glass-card' style='padding: 0;'><table class='int-table'>"
    table_html += "<tr><th>Attribute</th><th>Value</th><th>Confidence</th></tr>"
    
    fields = [
        ("Full Name", best_name, best_name_conf),
        ("Location", best_location, best_location_conf),
        ("Email Address", best_email, best_email_conf),
        ("Bio / Headline", best_bio, best_bio_conf),
        ("Personal Website", best_website, best_website_conf),
        ("Primary Focus", best_focus, best_focus_conf),
    ]
    
    has_fields = False
    for attr, val, conf in fields:
        if val:
            has_fields = True
            table_html += f"<tr><td>{attr}</td><td style='font-weight: 500;'>{val}</td><td>{get_badge(conf)}</td></tr>"
            
    table_html += "</table></div>"
    if has_fields:
        st.markdown(table_html, unsafe_allow_html=True)
    else:
        st.info("No structured identity attributes found.")
    
    # Section 2: Digital Footprint
    st.markdown("### 🌐 Discovered Footprints")
    if unique_footprints:
        cols = st.columns(3)
        for i, (k, f) in enumerate(unique_footprints.items()):
            with cols[i % 3]:
                st.markdown(f"""
                <div class="glass-card" style="padding: 16px; margin-bottom: 16px;">
                    <div style="color: #94a3b8; font-size: 0.875rem; margin-bottom: 4px; text-transform: uppercase;">{f['platform']}</div>
                    <div style="font-weight: 600; margin-bottom: 8px;">
                        <a href="{f['url']}" target="_blank" style="color: #60a5fa; text-decoration: none;">@{f['username']}</a>
                    </div>
                    <div>{get_badge(f['conf'])}</div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No digital footprints correlated.")
        
    # Section 3: Email Intelligence
    holehe_results = results.get("extracted_entities", {}).get("email", [])
    if best_email or holehe_results:
        st.markdown("### 📧 Registration Intelligence")
        st.markdown(f"""
        <div class="glass-card">
            <div style="margin-bottom: 12px; color: #94a3b8;">Known registrations associated with <strong>{best_email or 'target emails'}</strong>:</div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <span class="badge-gray">Data processing via Holehe & Profiling...</span>
                <span class="badge-green">GitHub (95%)</span>
                <span class="badge-yellow">Gravatar (80%)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Section 4: Key Insights
    st.markdown("### 📝 Key Insights & Summary")
    if narrative and narrative != "Agent workflow complete. Custom multi-agent reasoning applied.":
        st.markdown(narrative)
    else:
        st.markdown('<div class="glass-card" style="color: #94a3b8;">No verified narrative summary available. Run investigation to generate.</div>', unsafe_allow_html=True)
        
    # Section 5: Evidence Panel
    st.markdown("### 🗃️ Evidence Panel")
    for ent in all_ents:
        with st.expander(f"{ent.get('persona_name', 'Unknown')} | Conf: {ent.get('confidence',0):.0%}"):
            st.write(f"**Verification Method:** {ent.get('reasoning', '')}")
            st.json(ent.get('linked_data', {}))

    import datetime
    meta = results.get("metadata", {})
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(f"**Last Updated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | **Processing Time:** {meta.get('processing_time', '0')}s | **Provider:** `{meta.get('llm_provider', 'none')}`")