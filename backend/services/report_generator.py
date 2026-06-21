"""
Generate investigation reports
"""
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

import jinja2


class ReportGenerator:
    """
    Generate PDF and HTML reports
    """
    
    def __init__(self):
        self.template_dir = Path(__file__).parent / "templates"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
    
    def generate_investigation_report(
        self,
        case_data: Dict[str, Any],
        osint_results: List[Dict],
        network_data: Dict,
        output_format: str = "html"
    ) -> str:
        """
        Generate investigation report
        """
        report_data = {
            "generated_at": datetime.utcnow().isoformat(),
            "case": case_data,
            "osint_summary": self._summarize_osint(osint_results),
            "network_summary": self._summarize_network(network_data),
            "findings": osint_results,
            "social_media_links": self._extract_social_media(osint_results),
            "recommendations": self._generate_recommendations(osint_results)
        }
        
        if output_format == "html":
            return self._generate_html_report(report_data)
        elif output_format == "json":
            import json
            return json.dumps(report_data, indent=2)
        else:
            raise ValueError(f"Unsupported format: {output_format}")
            
    def _extract_social_media(self, results: List[Dict]) -> List[Dict]:
        """Extract all unique social media links from findings"""
        social_links = []
        seen_urls = set()
        
        for res in results:
            findings = res.get("findings", [])
            if not isinstance(findings, list):
                continue
            for sl in findings:
                if isinstance(sl, str):
                    url = sl
                    is_social = False
                    from backend.services.osint_engine import PLATFORM_DOMAINS
                    if any(domain in url.lower() for domain in PLATFORM_DOMAINS.keys()):
                        is_social = True
                    if is_social and url not in seen_urls:
                        social_links.append({"url": url, "category": "social", "platform": "Unknown"})
                        seen_urls.add(url)
                elif isinstance(sl, dict):
                    url = sl.get("url")
                    if not url or url in seen_urls:
                        continue
                    
                    is_social = sl.get("category") == "social"
                    if not is_social:
                        from backend.services.osint_engine import PLATFORM_DOMAINS
                        is_social = any(domain in url.lower() for domain in PLATFORM_DOMAINS.keys())
                    
                    if is_social:
                        social_links.append(sl)
                        seen_urls.add(url)
                    
        return social_links
    
    def _summarize_osint(self, results: List[Dict]) -> Dict[str, Any]:
        """Summarize OSINT findings"""
        total_findings = sum(len(r.get("findings", [])) for r in results)
        platforms_found = set()
        risk_scores = []
        
        for result in results:
            findings = result.get("findings", [])
            if isinstance(findings, list):
                for finding in findings:
                    if isinstance(finding, dict) and finding.get("platform"):
                        platforms_found.add(finding["platform"])
            if "risk_score" in result:
                risk_scores.append(result["risk_score"])
        
        return {
            "total_targets": len(results),
            "total_findings": total_findings,
            "unique_platforms": len(platforms_found),
            "platforms": list(platforms_found),
            "average_risk_score": sum(risk_scores) / len(risk_scores) if risk_scores else 0,
            "high_risk_count": sum(1 for r in results if r.get("risk_score", 0) > 0.7)
        }
    
    def _summarize_network(self, network_data: Dict) -> Dict[str, Any]:
        """Summarize network analysis"""
        nodes = network_data.get("nodes", [])
        edges = network_data.get("edges", [])
        
        return {
            "total_entities": len(nodes),
            "total_relationships": len(edges),
            "entity_types": len(set(n.get("group") for n in nodes)),
            "density": len(edges) / (len(nodes) * (len(nodes) - 1)) if len(nodes) > 1 else 0
        }
    
    def _generate_recommendations(self, results: List[Dict]) -> List[str]:
        """Generate investigation recommendations"""
        recommendations = []
        
        high_risk = [r for r in results if r.get("risk_score", 0) > 0.7]
        if high_risk:
            recommendations.append(
                f"Priority investigation required for {len(high_risk)} high-risk targets"
            )
        
        # Check for financial indicators
        financial_findings = []
        for r in results:
            findings = r.get("findings", [])
            if isinstance(findings, list):
                for f in findings:
                    if isinstance(f, dict) and f.get("platform") in ["paytm", "phonepe", "gpay", "paypal"]:
                        financial_findings.append(f)
        if financial_findings:
            recommendations.append(
                "Financial transaction analysis recommended - multiple payment platforms detected"
            )
        
        # Check for encrypted comms
        encrypted = []
        for r in results:
            findings = r.get("findings", [])
            if isinstance(findings, list):
                for f in findings:
                    if isinstance(f, dict) and f.get("platform") in ["telegram", "signal", "wickr"]:
                        encrypted.append(f)
        if encrypted:
            recommendations.append(
                "Encrypted communication platforms detected - consider device forensics"
            )
        
        return recommendations
    
    def _generate_html_report(self, data: Dict) -> str:
        """Generate HTML report"""
        template = self.env.get_template("report_template.html")
        return template.render(**data)
