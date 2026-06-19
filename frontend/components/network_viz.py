"""
Network visualization component
"""
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network
import json

from frontend.utils.api_client import api_client


def render_network_viz():
    """Render network visualization interface"""
    st.header("🕸️ Syndicate Network Analysis")
    
    # Controls
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Analysis Controls")
        
        analysis_type = st.selectbox(
            "Analysis Type",
            ["Entity Profile Viewer", "Single Entity Network", "Syndicate Detection", "Path Finder"]
        )
        
        if analysis_type == "Entity Profile Viewer":
            entity_id = st.text_input(
                "Entity ID or Name",
                placeholder="Enter name, email, phone, username, etc."
            )
            
            if st.button("View Profile", use_container_width=True):
                _load_network(entity_id, 1)
                
        elif analysis_type == "Single Entity Network":
            entity_id = st.text_input(
                "Entity ID or Name",
                placeholder="Enter entity identifier"
            )
            depth = st.slider("Network Depth", 1, 4, 2)
            
            if st.button("Generate Network", use_container_width=True):
                _load_network(entity_id, depth)
        
        elif analysis_type == "Syndicate Detection":
            min_connections = st.slider("Min Connections", 2, 10, 3)
            
            if st.button("Detect Syndicates", use_container_width=True):
                _detect_syndicates(min_connections)
        
        elif analysis_type == "Path Finder":
            source = st.text_input("Source Entity ID")
            target = st.text_input("Target Entity ID")
            
            if st.button("Find Path", use_container_width=True):
                _find_path(source, target)
        
        # Legend
        st.markdown("---")
        st.markdown("### Legend")
        legend_html = """
        <div style="font-size: 0.9em;">
        <span style="color: #3b82f6;">🔵</span> Person<br>
        <span style="color: #10b981;">🟢</span> Digital Identity<br>
        <span style="color: #ef4444;">🔴</span> Financial Instrument<br>
        <span style="color: #f59e0b;">🟡</span> Device<br>
        <span style="color: #8b5cf6;">🟣</span> Location
        </div>
        """
        st.markdown(legend_html, unsafe_allow_html=True)
    
    with col2:
        st.subheader("Results")
        
        if "network_data" in st.session_state and st.session_state.network_data:
            if analysis_type == "Entity Profile Viewer":
                _render_profile(st.session_state.network_data)
            else:
                _render_graph(st.session_state.network_data)
        else:
            st.info("Generate an analysis to see results")
        
        # Syndicate results
        if analysis_type == "Syndicate Detection" and "syndicates" in st.session_state and st.session_state.syndicates:
            _render_syndicates(st.session_state.syndicates)


def _load_network(entity_id: str, depth: int):
    """Load network data from API"""
    if not entity_id:
        st.error("Please enter an entity ID or name")
        return
    
    result = api_client.get(f"/api/v1/graph/network/{entity_id}", {"depth": depth}, timeout=120)
    
    if "error" in result:
        error_detail = result.get("detail") or result.get("error") or "Unknown error"
        st.error(f"Failed to load network: {error_detail}")
        return
    
    nodes = result.get("nodes", [])
    if not nodes:
        st.warning(f"No graph data found for '{entity_id}'. "
                   "Make sure the entity exists in the graph database and Neo4j is running.")
        return
    
    st.session_state.network_data = result



def _detect_syndicates(min_connections: int):
    """Detect criminal syndicates"""
    result = api_client.post("/api/v1/graph/syndicates", {
        "min_connections": min_connections
    })
    
    if "error" in result:
        st.error("Failed to detect syndicates")
        return
    
    st.session_state.syndicates = result.get("syndicates", [])


def _find_path(source: str, target: str):
    """Find path between entities"""
    if not source or not target:
        st.error("Please enter both source and target")
        return
    
    result = api_client.post("/api/v1/graph/path", {
        "source_id": source,
        "target_id": target
    })
    
    if "error" in result:
        st.error("No path found")
        return
    
    st.success(f"Path found! Length: {result.get('path_length', 0)}")
    st.json(result)

def _render_profile(network_data: dict):
    """Render a comprehensive profile view based on graph data"""
    nodes = network_data.get("nodes", [])
    if not nodes:
        st.info("No profile data found.")
        return
        
    # Assume the first node is the center (or find the one with the most edges)
    # The backend get_network_graph usually puts center node first, but let's find the one
    # that is connected to everything.
    edges = network_data.get("edges", [])
    if edges:
        from collections import Counter
        counts = Counter([e["from"] for e in edges] + [e["to"] for e in edges])
        center_id = counts.most_common(1)[0][0]
        center_node = next((n for n in nodes if n["id"] == center_id), nodes[0])
    else:
        center_node = nodes[0]
        
    props_str = center_node.get("title", "{}")
    try:
        import ast
        props = ast.literal_eval(props_str)
    except:
        props = {"raw": props_str}
        
    col_head1, col_head2 = st.columns([4, 1])
    with col_head1:
        st.markdown(f"### 👤 Profile: {center_node.get('label', 'Unknown')}")
        st.markdown(f"**Type:** `{center_node.get('group', 'Unknown')}`")
    with col_head2:
        if st.button("🗑️ Delete Entity", key=f"del_{center_node['id']}", type="secondary", use_container_width=True):
            with st.spinner("Deleting..."):
                del_result = api_client.delete(f"/api/v1/graph/entities/{center_node['id']}")
                if "error" not in del_result:
                    st.success("Entity deleted successfully!")
                    st.session_state.network_data = None
                    st.rerun()
                else:
                    st.error(f"Failed to delete: {del_result.get('detail', 'Unknown error')}")
    
    # Organize connected identifiers
    identifiers = {"Person": [], "DigitalIdentity": [], "Device": [], "Location": [], "FinancialInstrument": []}
    for n in nodes:
        if n["id"] != center_node["id"]:
            group = n.get("group", "Unknown")
            if group in identifiers:
                identifiers[group].append(n.get("label", n["id"]))
            else:
                identifiers.setdefault(group, []).append(n.get("label", n["id"]))
                
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 Primary Info")
        info_count = 0
        for k, v in props.items():
            if k not in ["id", "node_type"] and v and str(v).strip():
                st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                info_count += 1
        if info_count == 0:
            st.info("No additional properties available.")
                
        if identifiers["Location"]:
            st.markdown("---")
            st.subheader("📍 Locations")
            for loc in identifiers['Location']:
                st.markdown(f"- {loc}")
            
    with col2:
        st.subheader("🌐 Digital Footprint")
        
        def format_link(val):
            if val.startswith("http"):
                return f"[{val}]({val})"
            elif "@" in val and "." in val.split("@")[-1]:
                return f"[{val}](mailto:{val})"
            return f"`{val}`"
            
        has_footprint = False
        
        if identifiers["DigitalIdentity"]:
            has_footprint = True
            st.markdown("**Digital Identities & Emails**")
            for d in identifiers["DigitalIdentity"]:
                st.markdown(f"📧 {format_link(d)}")
                
        if identifiers["Device"]:
            has_footprint = True
            st.markdown("**Devices & IPs**")
            for d in identifiers["Device"]:
                st.markdown(f"💻 `{d}`")
                
        if identifiers["FinancialInstrument"]:
            has_footprint = True
            st.markdown("**Financial Instruments**")
            for d in identifiers["FinancialInstrument"]:
                st.markdown(f"💰 `{d}`")
                
        if not has_footprint:
            st.info("No digital footprint connected to this entity.")
                
    st.markdown("---")
    st.subheader("Raw Knowledge Graph JSON")
    with st.expander("View full graph data"):
        st.json(network_data)


def _render_graph(network_data: dict):
    """Render Pyvis network graph"""
    net = Network(
        height="600px",
        width="100%",
        bgcolor="#1a1a2e",
        font_color="#ffffff",
        directed=True
    )
    
    # Physics options
    net.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.08
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": {"iterations": 150}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 200
      }
    }
    """)
    
    # Color mapping
    color_map = {
        "Person": "#3b82f6",
        "DigitalIdentity": "#10b981",
        "FinancialInstrument": "#ef4444",
        "Device": "#f59e0b",
        "Location": "#8b5cf6",
        "Unknown": "#6b7280"
    }
    
    # Add nodes
    for node in network_data.get("nodes", []):
        node_size = node.get("value", 20)
        color = color_map.get(node.get("group"), "#6b7280")
        
        net.add_node(
            node["id"],
            label=node.get("label", node["id"]),
            title=node.get("title", ""),
            color=color,
            size=node_size,
            font={"color": "#ffffff", "size": 14}
        )
    
    # Add edges
    for edge in network_data.get("edges", []):
        net.add_edge(
            edge["from"],
            edge["to"],
            title=edge.get("label", ""),
            color="#4b5563",
            arrows="to"
        )
    
    # Save and display
    net.save_graph("network.html")
    
    with open("network.html", "r", encoding="utf-8") as f:
        html = f.read()
        components.html(html, height=600)


def _render_syndicates(syndicates: list):
    """Render detected syndicates"""
    st.markdown("### 🚨 Detected Syndicates")
    
    if not syndicates:
        st.info("No syndicates detected with current parameters")
        return
    
    for i, syndicate in enumerate(syndicates, 1):
        with st.expander(f"Syndicate #{i}: {syndicate.get('name', 'Unnamed')}"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Members", syndicate.get("member_count", 0))
            with col2:
                st.metric("Density", f"{syndicate.get('density', 0):.2f}")
            with col3:
                st.metric("Risk Score", f"{syndicate.get('risk_score', 0):.2f}")
            
            st.markdown("**Members:**")
            members = syndicate.get("members", [])
            st.write(", ".join(members[:10]))