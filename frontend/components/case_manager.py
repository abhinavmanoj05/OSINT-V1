"""
Case management component
"""
import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional

from frontend.utils.api_client import api_client


def render_case_manager():
    """Render case management interface"""
    st.header("Case Management")

    tab1, tab2, tab3 = st.tabs(["Create Case", "View Cases", "Case Details"])

    with tab1:
        _render_create_case()

    with tab2:
        _render_case_list()

    with tab3:
        _render_case_details()


# ---------------------------------------------------------------------------
# Target profile fields (reused in create + edit)
# ---------------------------------------------------------------------------

def _render_target_profile_form(prefix: str = "", defaults: Optional[Dict] = None) -> Dict:
    """
    Render the suspect / target profile sub-form.
    Returns a dict with all filled values (omits empty strings).
    `prefix` is used to namespace Streamlit widget keys so the same form
    can appear in both create and edit contexts without key collisions.
    """
    d = defaults or {}

    st.markdown("#### Suspect / Target Profile")
    st.caption(
        "Fill in as many identifiers as known. These seed the OSINT engine automatically "
        "when you launch an investigation from this case."
    )

    # ── Row 1: personal identifiers ─────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        name = st.text_input(
            "Full Name", value=d.get("name", ""),
            placeholder="e.g. Ravi Kumar",
            key=f"{prefix}tp_name"
        )
    with c2:
        username = st.text_input(
            "Username / Handle", value=d.get("username", ""),
            placeholder="e.g. ravi_k_2024",
            key=f"{prefix}tp_username"
        )
    with c3:
        aliases_raw = st.text_input(
            "Aliases (comma-separated)", value=", ".join(d.get("aliases", [])),
            placeholder="e.g. RK, ravi.kumar99",
            key=f"{prefix}tp_aliases"
        )

    # ── Row 2: contact / digital ─────────────────────────────────────────────
    c4, c5, c6 = st.columns(3)
    with c4:
        email = st.text_input(
            "Email Address", value=d.get("email", ""),
            placeholder="e.g. ravi@gmail.com",
            key=f"{prefix}tp_email"
        )
    with c5:
        phone = st.text_input(
            "Phone Number", value=d.get("phone", ""),
            placeholder="e.g. +919876543210",
            key=f"{prefix}tp_phone"
        )
    with c6:
        ip_address = st.text_input(
            "IP Address", value=d.get("ip_address", ""),
            placeholder="e.g. 192.168.1.1",
            key=f"{prefix}tp_ip"
        )

    # ── Row 3: financial identifiers ─────────────────────────────────────────
    c7, c8, c9 = st.columns(3)
    with c7:
        upi_id = st.text_input(
            "UPI ID", value=d.get("upi_id", ""),
            placeholder="e.g. ravi@paytm",
            key=f"{prefix}tp_upi"
        )
    with c8:
        bank_account = st.text_input(
            "Bank Account No.", value=d.get("bank_account", ""),
            placeholder="e.g. 50100123456789",
            key=f"{prefix}tp_bank"
        )
    with c9:
        crypto_wallet = st.text_input(
            "Crypto Wallet", value=d.get("crypto_wallet", ""),
            placeholder="e.g. 1A1zP1eP...",
            key=f"{prefix}tp_crypto"
        )

    # ── Row 4: technical / location ───────────────────────────────────────────
    c10, c11 = st.columns(2)
    with c10:
        domain = st.text_input(
            "Domain / Website", value=d.get("domain", ""),
            placeholder="e.g. scamsite.com",
            key=f"{prefix}tp_domain"
        )
    with c11:
        institution = st.text_input(
            "Institution / Organization", value=d.get("institution", ""),
            placeholder="e.g. TCS, IIT Bombay",
            key=f"{prefix}tp_institution"
        )

    location = st.text_input(
        "Location / Area", value=d.get("location", ""),
        placeholder="e.g. Ernakulam, Kerala",
        key=f"{prefix}tp_location"
    )

    modus_operandi = st.text_area(
        "Modus Operandi / Behavioral Notes",
        value=d.get("modus_operandi", ""),
        placeholder=(
            "Describe how the suspect operates — e.g. contacts victims via WhatsApp, "
            "uses OTP forwarding scam, active 10PM-2AM..."
        ),
        height=80,
        key=f"{prefix}tp_modus"
    )

    notes = st.text_area(
        "Additional Notes",
        value=d.get("notes", ""),
        placeholder="Any other observations, cross-references, or intelligence tips…",
        height=68,
        key=f"{prefix}tp_notes"
    )

    # Build result dict — skip empty values
    aliases_list = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    profile: Dict = {}
    for key, val in [
        ("name", name), ("username", username), ("email", email),
        ("phone", phone), ("ip_address", ip_address), ("upi_id", upi_id),
        ("bank_account", bank_account), ("crypto_wallet", crypto_wallet),
        ("domain", domain), ("institution", institution),
        ("location", location), ("modus_operandi", modus_operandi),
        ("notes", notes),
    ]:
        if val and val.strip():
            profile[key] = val.strip()
    if aliases_list:
        profile["aliases"] = aliases_list

    return profile


# ---------------------------------------------------------------------------
# Create Case tab
# ---------------------------------------------------------------------------

def _render_create_case():
    """Render case creation form"""
    st.subheader("Create New Investigation Case")

    with st.form("create_case_form"):
        # ── Case metadata ────────────────────────────────────────────────────
        col1, col2 = st.columns(2)
        with col1:
            case_number = st.text_input(
                "FIR Number *",
                placeholder="KER/2024/XXXXX",
                help="Enter the official FIR number"
            )
            title = st.text_input(
                "Case Title *",
                placeholder="Brief description of the case"
            )
        with col2:
            crime_type = st.selectbox(
                "Crime Type",
                ["Financial Fraud", "Phishing", "Identity Theft",
                 "Cyberbullying", "Ransomware", "Data Breach", "Other"]
            )
            priority = st.slider("Priority", 1, 5, 3)

        description = st.text_area(
            "Case Description",
            placeholder="Detailed description of the incident..."
        )

        assigned_officer = st.text_input(
            "Assigned Officer",
            placeholder="Officer name/badge number"
        )

        st.markdown("---")

        # ── Target profile (inline — inside the same form) ───────────────────
        target_profile = _render_target_profile_form(prefix="create_")

        submitted = st.form_submit_button("🚀 Create Case", use_container_width=True, type="primary")

        if submitted:
            if not case_number or not title:
                st.error("FIR Number and Title are required!")
                return

            case_data = {
                "case_number": case_number,
                "title": title,
                "description": description,
                "crime_type": crime_type,
                "priority": priority,
                "assigned_officer": assigned_officer or "Unassigned",
                "status": "open",
                "target_profile": target_profile,
            }

            result = api_client.post("/api/v1/cases/", case_data)

            if "error" not in result:
                st.success(
                    f"✅ Case **{case_number}** created successfully! "
                    "Navigate to *Case Details* tab to launch an investigation."
                )
                # Make this case active across all modules
                for key in ("current_case", "selected_case", "investigation_case",
                            "evidence_case", "network_case"):
                    st.session_state[key] = result
            else:
                st.error(f"Failed to create case: {result.get('detail', 'Unknown error')}")


# ---------------------------------------------------------------------------
# View Cases tab
# ---------------------------------------------------------------------------

def _render_case_list():
    """Render list of cases"""
    st.subheader("Active Cases")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["All", "open", "closed", "pending"])
    with col2:
        crime_filter = st.selectbox(
            "Crime Type",
            ["All", "Financial Fraud", "Phishing", "Identity Theft",
             "Cyberbullying", "Ransomware", "Data Breach", "Other"]
        )
    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # Fetch
    params = {}
    if status_filter != "All":
        params["status"] = status_filter
    if crime_filter != "All":
        params["crime_type"] = crime_filter

    result = api_client.get("/api/v1/cases/", params)

    if "error" in result:
        st.error("Failed to load cases — is the backend running?")
        return

    cases = result.get("cases", [])

    if not cases:
        st.info("No cases found. Create one using the **➕ Create Case** tab.")
        return

    import pandas as pd

    df = pd.DataFrame([
        {
            "Case #": c["case_number"],
            "Title": c["title"],
            "Type": c["crime_type"],
            "Status": c["status"],
            "Priority": "🔴" * c["priority"] + "⚪" * (5 - c["priority"]),
            "Officer": c["assigned_officer"],
            "Target": _summarise_target(c.get("target_profile") or {}),
            "Created": c["created_at"][:10] if c["created_at"] else "",
        }
        for c in cases
    ])

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Selection
    case_numbers = [c["case_number"] for c in cases]
    selected = st.selectbox("Select case to view details →", ["-- Select --"] + case_numbers)

    if selected != "-- Select --":
        selected_case = next(c for c in cases if c["case_number"] == selected)
        # Update all relevant session state variables so the selection persists across all modules
        for key in ("current_case", "selected_case", "investigation_case", "evidence_case", "network_case"):
            st.session_state[key] = selected_case
        st.success(f"Case **{selected}** loaded — switch to the **🔍 Case Details** tab.")


def _summarise_target(profile: Dict) -> str:
    """One-line summary of target profile for the table column."""
    parts = []
    if profile.get("name"):
        parts.append(profile["name"])
    if profile.get("username"):
        parts.append(f"@{profile['username']}")
    if profile.get("phone"):
        parts.append(profile["phone"])
    if profile.get("email"):
        parts.append(profile["email"])
    return " | ".join(parts[:3]) or "—"


# ---------------------------------------------------------------------------
# Case Details tab
# ---------------------------------------------------------------------------

def _render_case_details():
    """Render detailed case view with target profile editing"""
    if "selected_case" not in st.session_state or not st.session_state.selected_case:
        st.info("Select a case from the **📋 View Cases** tab to see details here.")
        return

    case = st.session_state.selected_case
    target_profile: Dict = case.get("target_profile") or {}

    st.subheader(f"📁 Case: {case['case_number']} — {case['title']}")

    # ── Status / priority metrics ────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        status_color = {"open": "🟢", "closed": "🔴", "pending": "🟡"}.get(case["status"], "⚪")
        st.metric("Status", f"{status_color} {case['status'].upper()}")
    with col2:
        st.metric("Priority", "🔴" * case["priority"] + "⚪" * (5 - case["priority"]))
    with col3:
        st.metric("Assigned Officer", case["assigned_officer"] or "Unassigned")

    st.markdown(f"**Crime Type:** `{case.get('crime_type', 'N/A')}`")
    st.markdown("### 📝 Description")
    st.write(case["description"] or "No description provided.")

    # ── Target Profile display ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Suspect / Target Profile")

    if target_profile:
        _display_target_profile(target_profile)
    else:
        st.info("No target profile recorded for this case.")

    # ── Edit target profile / case details ──────────────────────────────────
    with st.expander("✏️ Edit Case Details & Target Profile", expanded=False):
        with st.form(f"edit_case_{case['id']}"):
            ec1, ec2 = st.columns(2)
            with ec1:
                new_status = st.selectbox(
                    "Status", ["open", "closed", "pending"],
                    index=["open", "closed", "pending"].index(case.get("status", "open"))
                )
                new_priority = st.slider("Priority", 1, 5, case.get("priority", 3))
            with ec2:
                new_officer = st.text_input(
                    "Assigned Officer",
                    value=case.get("assigned_officer") or ""
                )
                new_title = st.text_input("Case Title", value=case.get("title", ""))

            new_description = st.text_area(
                "Description", value=case.get("description") or "", height=80
            )

            st.markdown("---")
            new_tp = _render_target_profile_form(
                prefix=f"edit_{case['id']}_", defaults=target_profile
            )

            if st.form_submit_button("💾 Save Changes", use_container_width=True, type="primary"):
                update_payload = {
                    "title": new_title,
                    "description": new_description,
                    "status": new_status,
                    "priority": new_priority,
                    "assigned_officer": new_officer,
                    "target_profile": new_tp,
                }
                upd_result = api_client.put(f"/api/v1/cases/{case['id']}", update_payload)
                if "error" not in upd_result:
                    st.success("✅ Case updated successfully!")
                    # Refresh local session state
                    st.session_state.selected_case = upd_result
                    for key in ("current_case", "investigation_case",
                                "evidence_case", "network_case"):
                        state_val = st.session_state.get(key)
                        if state_val and isinstance(state_val, dict) and state_val.get("id") == case["id"]:
                            st.session_state[key] = upd_result
                    st.rerun()
                else:
                    st.error(f"Update failed: {upd_result.get('detail', 'Unknown error')}")

    # ── Quick action buttons ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚡ Quick Actions")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔍 Start OSINT Investigation", use_container_width=True, type="primary"):
            st.session_state.investigation_case = case
            # Pre-fill OSINT form with primary target identifier
            primary_id, primary_type = _pick_primary_identifier(target_profile)
            if primary_id:
                st.session_state.osint_prefill_target = primary_id
                st.session_state.osint_prefill_type = primary_type
            st.session_state.current_page = "🔍 OSINT Investigation"
            st.rerun()
    with col2:
        if st.button("🕸️ View Network Graph", use_container_width=True):
            st.session_state.network_case = case
            st.session_state.current_page = "🕸️ Network Analysis"
            st.rerun()
    with col3:
        if st.button("📄 Upload Evidence", use_container_width=True):
            st.session_state.evidence_case = case
            st.session_state.current_page = "📄 Document Intelligence"
            st.rerun()


def _display_target_profile(profile: Dict):
    """Render a read-only summary card for the target profile."""
    field_labels = [
        ("name",            "👤 Full Name"),
        ("aliases",         "🔤 Aliases"),
        ("username",        "💻 Username"),
        ("email",           "📧 Email"),
        ("phone",           "📱 Phone"),
        ("upi_id",          "💳 UPI ID"),
        ("bank_account",    "🏦 Bank Account"),
        ("crypto_wallet",   "₿ Crypto Wallet"),
        ("ip_address",      "🌐 IP Address"),
        ("domain",          "🌍 Domain"),
        ("institution",     "🏢 Institution"),
        ("location",        "📍 Location"),
        ("modus_operandi",  "⚠️ Modus Operandi"),
        ("notes",           "📌 Notes"),
    ]

    filled = [(lbl, profile[key]) for key, lbl in field_labels if profile.get(key)]
    if not filled:
        st.info("Target profile is empty — use the edit form below to add suspect details.")
        return

    # Display in two-column grid
    left, right = [], []
    for i, item in enumerate(filled):
        (left if i % 2 == 0 else right).append(item)

    c1, c2 = st.columns(2)
    with c1:
        for label, value in left:
            if isinstance(value, list):
                value = ", ".join(value)
            st.markdown(f"**{label}:** `{value}`")
    with c2:
        for label, value in right:
            if isinstance(value, list):
                value = ", ".join(value)
            st.markdown(f"**{label}:** `{value}`")


def _pick_primary_identifier(profile: Dict):
    """Return (value, type) of the most useful identifier for OSINT seeding."""
    priority_order = [
        ("username", "Username"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("upi_id", "UPI ID"),
        ("name", "Name"),
        ("ip_address", "IP Address"),
        ("domain", "Domain"),
        ("bank_account", "Bank Account"),
    ]
    for key, label in priority_order:
        if profile.get(key):
            return profile[key], label
    return None, "Auto-Detect"