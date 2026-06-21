"""
Crime Analysis Mapper - Streamlit Frontend
Main application entry point
"""
import streamlit as st
import sys
import os
from typing import Optional

# Add project root to path to resolve frontend imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from frontend.utils.api_client import api_client
from frontend.components.case_manager import render_case_manager
from frontend.components.osint_panel import render_osint_panel
from frontend.components.network_viz import render_network_viz
from frontend.components.document_upload import render_document_upload

# Page configuration
st.set_page_config(
    page_title="Kerala Cyber Police - Crime Analysis Mapper",
    page_icon="🕵️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        text-align: center;
        padding: 1rem;
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        color: white;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .stButton>button {
        background-color: #1e3a8a;
        color: white;
        font-weight: bold;
        border-radius: 5px;
    }
    .stButton>button:hover {
        background-color: #2563eb;
    }
    .css-1d391kg {
        padding-top: 1rem;
    }
    .risk-high { color: #dc2626; font-weight: bold; }
    .risk-medium { color: #d97706; font-weight: bold; }
    .risk-low { color: #16a34a; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables"""
    defaults = {
        'current_page': '📁 Case Management',
        'current_case': None,
        'selected_case': None,
        'investigation_case': None,
        'network_case': None,
        'evidence_case': None,
        'last_investigation': None,
        'last_document_result': None,
        'network_data': None,
        'syndicates': None,
        'api_token': None,
        'osint_prefill_target': '',
        'osint_prefill_type': 'Auto-Detect',
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_sidebar():
    """Render navigation sidebar"""
    with st.sidebar:
        # Logo/Header
        st.markdown("""
        <div style="text-align: center; padding: 1rem 0;">
            <h2 style="color: #1e3a8a; margin: 0;">🕵️</h2>
            <h3 style="color: #1e3a8a; margin: 0; font-size: 1.1rem;">Crime Analysis Mapper</h3>
            <p style="color: #6b7280; font-size: 0.8rem; margin: 0;">Kerala Cyber Police</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Navigation
        st.title("Navigation")
        
        pages = [
            "📁 Case Management",
            "🔍 OSINT Investigation", 
            "🕸️ Network Analysis",
            "📄 Document Intelligence",
            "📊 Reports"
        ]
        
        selected = st.radio(
            "Select Module",
            pages,
            index=pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0
        )
        
        if selected != st.session_state.current_page:
            st.session_state.current_page = selected
            st.rerun()
        
        st.markdown("---")
        
        # Quick Stats
        st.markdown("### System Status")
        # Real connectivity check
        try:
            import requests as _req
            resp = _req.get("http://localhost:8000/health", timeout=2)
            if resp.status_code == 200:
                st.success("🟢 API Connected (port 8000)")
            else:
                st.warning(f"🟡 API responded with status {resp.status_code}")
        except Exception:
            st.error("🔴 API Offline — Start backend server")
        
        col1, col2 = st.columns(2)
        with col1:
            try:
                import requests as _req2
                cr = _req2.get("http://localhost:8000/api/v1/cases/",
                               headers={"Content-Type": "application/json"}, timeout=2)
                if cr.status_code == 200:
                    st.metric("Active Cases", cr.json().get("total", "—"))
                else:
                    st.metric("Active Cases", "—")
            except Exception:
                st.metric("Active Cases", "—")
        with col2:
            st.metric("Entities", "—")
        
        # Current case indicator
        if st.session_state.current_case:
            st.markdown("---")
            st.markdown("### Current Case")
            case = st.session_state.current_case
            st.info(f"**{case.get('case_number', 'N/A')}**\n{case.get('title', '')[:30]}...")
        
        st.markdown("---")
        st.caption("v1.0.0 | Kerala Cyber Police Division")


def render_header():
    """Render main header"""
    st.markdown("""
    <div class="main-header">
        🕵️ Crime Analysis Mapper<br>
        <span style="font-size: 0.6em; opacity: 0.9;">
            Kerala Cyber Police Division - OSINT Investigation Platform
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_footer():
    """Render footer"""
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #6b7280; font-size: 0.8rem;">
        <p>© 2024 Kerala Cyber Police Division | Confidential - Authorized Use Only</p>
        <p>All activities are logged for audit and legal compliance</p>
    </div>
    """, unsafe_allow_html=True)


def main():
    """Main application"""
    init_session_state()
    render_sidebar()
    
    # Render current page
    page = st.session_state.current_page
    
    if "Case Management" in page:
        render_case_manager()
    elif "OSINT Investigation" in page:
        render_osint_panel()
    elif "Network Analysis" in page:
        render_network_viz()
    elif "Document Intelligence" in page:
        render_document_upload()
    else:
        st.header("📊 Reports")
        
        # Fetch cases for dropdown
        result = api_client.get("/api/v1/cases/")
        cases = result.get("cases", []) if isinstance(result, dict) and "error" not in result else []
        
        case = st.session_state.get("selected_case") or st.session_state.get("current_case") or st.session_state.get("investigation_case")
        
        if cases:
            case_options = [c["case_number"] for c in cases]
            current_index = 0
            if case and case["case_number"] in case_options:
                current_index = case_options.index(case["case_number"]) + 1
                
            selected_case_num = st.selectbox("Select Case", ["-- Select --"] + case_options, index=current_index)
            
            if selected_case_num != "-- Select --":
                if not case or case["case_number"] != selected_case_num:
                    new_case = next(c for c in cases if c["case_number"] == selected_case_num)
                    for key in ("current_case", "selected_case", "investigation_case", "evidence_case", "network_case"):
                        st.session_state[key] = new_case
                    case = new_case
                    st.rerun() # Force rerun to ensure state is cleanly propagated
        else:
            st.warning("No cases found in the system. Create one in Case Management.")
            
        if not case or (cases and selected_case_num == "-- Select --"):
            st.info("Please select a case from the dropdown above to generate a report.")
        else:
            st.info(f"Generating report for Case: **{case['case_number']}**")
            
            col1, col2 = st.columns(2)
            with col1:
                report_type = st.selectbox("Report Type", [
                    "Full Investigation Report",
                    "OSINT Summary Report",
                    "Network Analysis Report"
                ])
            with col2:
                report_format = st.selectbox("Format", ["HTML", "PDF", "JSON"])
            
            if st.button("Generate & View Report", use_container_width=True, type="primary"):
                with st.spinner("Generating report..."):
                    fmt = report_format.lower()
                    type_mapping = {
                        "Full Investigation Report": "full",
                        "OSINT Summary Report": "osint",
                        "Network Analysis Report": "network"
                    }
                    r_type = type_mapping.get(report_type, "full")
                    url = f"/api/v1/reports/{case['id']}?format={fmt}&report_type={r_type}"
                    
                    if fmt == "html":
                        response = api_client.get(url)
                        if "error" not in response:
                            st.success("Report generated successfully!")
                            st.download_button(
                                "Download HTML Report",
                                data=response if isinstance(response, str) else str(response),
                                file_name=f"Report_{case['case_number']}.html",
                                mime="text/html"
                            )
                            with st.expander("Report Preview"):
                                st.components.v1.html(response if isinstance(response, str) else str(response), height=600, scrolling=True)
                    elif fmt == "pdf":
                        # The API returns the raw PDF binary content
                        import requests
                        base_url = "http://localhost:8000"
                        headers = {"Authorization": f"Bearer {st.session_state.api_token}"} if st.session_state.api_token else {}
                        resp = requests.get(f"{base_url}{url}", headers=headers)
                        
                        if resp.status_code == 200:
                            st.success("PDF Report generated successfully!")
                            st.download_button(
                                "Download PDF Report",
                                data=resp.content,
                                file_name=f"Report_{case['case_number']}.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("Failed to generate PDF report.")
                    else:
                        result = api_client.get(url)
                        if "error" not in result:
                            st.success("Report generated successfully!")
                            st.json(result)
                            st.download_button(
                                "Download JSON Report",
                                data=str(result),
                                file_name=f"Report_{case['case_number']}.json",
                                mime="application/json"
                            )


if __name__ == "__main__":
    main()