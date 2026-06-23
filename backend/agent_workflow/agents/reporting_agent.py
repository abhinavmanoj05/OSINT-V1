import os
import json
from datetime import datetime

class ReportingAgent:
    """
    Final agent in the workflow graph that takes the correlation JSON output
    and generates a beautifully formatted Markdown dossier.
    """
    
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def generate_dossier(self, correlation_json: dict, target_name: str = "Unknown_Target") -> str:
        """
        Generates a professional Markdown dossier and writes it to disk.
        Converts to PDF using markdown-pdf.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{target_name}_Dossier_{timestamp}.md"
        filepath = os.path.join(self.output_dir, filename)
        
        summary = correlation_json.get("narrative_summary", "No summary provided.")
        nodes = correlation_json.get("nodes", [])
        edges = correlation_json.get("edges", [])
        
        md_lines = []
        md_lines.append(f"# 🕵️ OSINT Target Dossier: {target_name}")
        md_lines.append(f"**Generated On:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        md_lines.append("\n## 📄 Executive Summary\n")
        md_lines.append(summary)
        
        # Calculate a mock confidence score based on data richness
        confidence_score = min(99, 40 + (len(nodes) * 5) + (len(edges) * 10))
        risk_level = "HIGH" if confidence_score > 80 else "MEDIUM" if confidence_score > 60 else "LOW"
        
        md_lines.append("\n## 🎯 Cyber Profiler Confidence Assessment\n")
        md_lines.append(f"**Overall Confidence Score:** {confidence_score}%\n")
        md_lines.append(f"**Risk Level:** {risk_level}\n")
        md_lines.append("> *Assessment based on the density of correlated cross-platform footprint and linked entities.*")

        
        md_lines.append("\n## 🔍 Extracted Entities & Digital Footprints\n")
        md_lines.append("| ID | Entity Type | Details / Attributes |")
        md_lines.append("|---|---|---|")
        for node in nodes:
            node_id = node.get("id", "N/A")
            # Handle both graph.py schema and reports.py schema
            node_type = node.get("type", node.get("group", "Unknown"))
            
            # Format attributes cleanly
            attrs = node.get("attributes", {})
            if not attrs and "label" in node:
                attrs = {"label": node.get("label")}
                
            if isinstance(attrs, dict):
                attr_str = "<br>".join([f"**{k}**: {v}" for k, v in attrs.items() if v])
            else:
                attr_str = str(attrs)
                
            md_lines.append(f"| `{node_id}` | **{node_type}** | {attr_str or 'None'} |")
            
        md_lines.append("\n## 🕸️ Identified Connections (Graph)\n")
        md_lines.append("| Source Entity | Relation | Target Entity |")
        md_lines.append("|---|---|---|")
        for edge in edges:
            # Handle both graph.py schema and reports.py schema
            src = edge.get("source", edge.get("from", "N/A"))
            tgt = edge.get("target", edge.get("to", "N/A"))
            rel = edge.get("relation", edge.get("label", "LINKED"))
            md_lines.append(f"| `{src}` | **{rel}** | `{tgt}` |")
            
        md_lines.append("\n## 📋 Investigation Timeline\n")
        md_lines.append(f"- **{datetime.utcnow().strftime('%Y-%m-%d')}**: Automated OSINT profiling initiated for {target_name}.")
        md_lines.append(f"- **{datetime.utcnow().strftime('%Y-%m-%d')}**: Cross-platform correlation and entity extraction completed.")
        if edges:
            md_lines.append(f"- **{datetime.utcnow().strftime('%Y-%m-%d')}**: {len(edges)} connections mapped.")
            
        md_lines.append("\n---\n*Report generated automatically by the Crime Analysis Mapper - Reporting Agent.*")
        
        dossier_content = "\n".join(md_lines)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(dossier_content)
            
        # Also generate PDF
        try:
            from markdown_pdf import MarkdownPdf, Section
            pdf = MarkdownPdf(toc_level=2)
            pdf.add_section(Section(dossier_content))
            pdf_filepath = filepath.replace(".md", ".pdf")
            pdf.save(pdf_filepath)
            print(f"[Reporting Agent] PDF Dossier also generated at: {pdf_filepath}")
        except Exception as e:
            print(f"[Reporting Agent] Failed to generate PDF: {e}")
            
        return filepath

# Instantiate a global instance or a factory similar to other agents
reporting_agent = ReportingAgent()
