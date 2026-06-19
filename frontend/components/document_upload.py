"""
Document upload and processing component
"""
import streamlit as st
import pandas as pd
from typing import Dict, Optional

from frontend.utils.api_client import api_client


def render_document_upload():
    """Render document upload interface"""
    st.header("📄 Document Intelligence")
    
    case = st.session_state.get("evidence_case")
    is_quick_upload = False
    
    if not case:
        st.info("No case selected. Running in **Quick Upload** mode. (Document will be available globally for cross-referencing)")
        is_quick_upload = True
    else:
        st.info(f"Uploading evidence for Case: **{case['case_number']}**")
        if st.button("Switch to Quick Upload (Clear Case)"):
            st.session_state.evidence_case = None
            st.rerun()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Upload Evidence")
        
        uploaded_file = st.file_uploader(
            "Choose file",
            type=["pdf", "png", "jpg", "jpeg", "tiff"],
            help="Upload case files, bank statements, screenshots, etc."
        )
        
        if uploaded_file:
            st.success(f"Selected: {uploaded_file.name}")
            
            extract_options = st.multiselect(
                "Extraction Options",
                ["OCR Text", "Tables", "Entities", "Financial Data"],
                default=["OCR Text", "Entities"]
            )
            
            if st.button("Process Document", use_container_width=True, type="primary"):
                _process_document(case.get("id") if case else None, uploaded_file)
    
    with col2:
        if st.session_state.get("last_document_result") is not None:
            _render_document_results(st.session_state.last_document_result)
        else:
            st.info("Upload and process a document to see extracted intelligence")


def _process_document(case_id: Optional[str], uploaded_file):
    """Process uploaded document"""
    with st.spinner("Processing document... This may take a minute"):
        # Prepare file for upload
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
        
        url = "/api/v1/documents/upload"
        if case_id:
            url += f"?case_id={case_id}"
            
        result = api_client.post(url, files=files)
        
        if "error" in result:
            st.error(f"Processing failed: {result.get('detail', 'Unknown error')}")
            return
        
        st.session_state.last_document_result = result
        st.success("Document processed successfully!")


def _render_document_results(result: Dict):
    """Render document processing results"""
    st.subheader("Extracted Intelligence")
    
    processing = result.get("processing_result", {})
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        entities_count = len(processing.get("extracted_entities", []))
        st.metric("Entities Found", entities_count)
    with col2:
        ocr_results = processing.get("ocr_results", [])
        avg_confidence = sum(r.get("confidence", 0) for r in ocr_results) / len(ocr_results) if ocr_results else 0
        st.metric("OCR Confidence", f"{avg_confidence:.0%}")
    with col3:
        processing_time = processing.get("processing_time", 0)
        st.metric("Processing Time", f"{processing_time:.1f}s")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Extracted Text", "LLM Entities", "Targets", "Topics & Themes", "Metadata"])
    
    with tab1:
        ocr_results = processing.get("ocr_results", [])
        if ocr_results:
            text = "\n\n".join([r.get("text", "") for r in ocr_results])
            st.text_area("OCR Text", text, height=300)
        else:
            st.info("No text extracted")
    
    with tab2:
        llm_analysis = processing.get("llm_analysis", {})
        llm_entities = llm_analysis.get("related_entities", {}) if llm_analysis else {}
        
        # Display regex entities as fallback if no LLM entities
        regex_entities = processing.get("extracted_entities", [])
        
        if llm_entities:
            st.markdown("### 🧠 LLM-Extracted Entities")
            for category, items in llm_entities.items():
                if items:
                    st.markdown(f"**{category.replace('_', ' ').title()}**")
                    st.write(", ".join(items))
            st.markdown("---")
        
        if regex_entities:
            st.markdown("### 🔍 Regex Extracted Entities")
            df = pd.DataFrame([
                {
                    "Type": e.get("entity_type", "Unknown"),
                    "Value": e.get("value", ""),
                    "Confidence": f"{e.get('confidence', 0):.0%}",
                    "Context": e.get("context", "")[:50] + "..."
                }
                for e in regex_entities
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Quick actions for entities
            st.markdown("### Quick Actions")
            for idx, entity in enumerate(regex_entities[:5]):  # Top 5 entities
                entity_type = entity.get("entity_type")
                value = entity.get("value", "")
                label = f"Investigate {entity_type}: {value[:20]}{'...' if len(value) > 20 else ''}"
                if st.button(label, key=f"btn_{idx}_{value[:30]}"):
                    st.session_state.investigation_target = {
                        "type": entity_type,
                        "value": value
                    }
                    st.info(f"Added {value} to investigation queue")
        else:
            if not llm_entities:
                st.info("No entities extracted")

    with tab3:
        llm_analysis = processing.get("llm_analysis", {})
        targets = llm_analysis.get("targets_identified", []) if llm_analysis else []
        
        if targets:
            for idx, target in enumerate(targets):
                name = target.get("name", "Unknown")
                role = target.get("role", "Unknown Role")
                context = target.get("context", "")
                
                with st.expander(f"🎯 {name} - {role}", expanded=True):
                    st.write(f"**Context:** {context}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(f"Add {name} to Case Management", key=f"seed_case_{idx}_{name}"):
                            # Pre-fill for Case Management
                            st.info(f"Seed functionality for {name} clicked! Target can be added to Case Management.")
                    with c2:
                        if st.button(f"Investigate {name} via OSINT", key=f"investigate_osint_{idx}_{name}"):
                            # Pre-fill for OSINT Panel
                            st.session_state.osint_prefill_target = name
                            st.session_state.osint_prefill_type = "Name"
                            st.session_state.current_page = "🔍 OSINT Investigation"
                            st.rerun()
        else:
            st.info("No explicit targets identified by LLM analysis.")

    with tab4:
        llm_analysis = processing.get("llm_analysis", {})
        topics = llm_analysis.get("topics_and_themes", {}) if llm_analysis else {}
        summary = llm_analysis.get("summary", "") if llm_analysis else ""
        
        if summary:
            st.markdown("### 📝 Summary")
            st.write(summary)
            st.markdown("---")
            
        if topics:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Crimes/Violations:**")
                for c in topics.get("crimes", []):
                    st.markdown(f"- {c}")
                st.markdown("**Categories:**")
                for c in topics.get("categories", []):
                    st.markdown(f"- {c}")
            with c2:
                st.markdown("**Events:**")
                for e in topics.get("events", []):
                    st.markdown(f"- {e}")
                st.markdown("**Main Themes:**")
                for t in topics.get("main_themes", []):
                    st.markdown(f"- {t}")
        else:
            st.info("No topics or themes extracted.")
    
    with tab5:
        metadata = processing.get("metadata", {})
        st.json(metadata)
    
    # Actions
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add Entities to Case", use_container_width=True):
            st.success("Entities linked to case")
    with col2:
        if st.button("Reprocess with Different Settings", use_container_width=True):
            st.info("Reprocessing started")