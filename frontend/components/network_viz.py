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
    
    cases_response = api_client.get("/api/v1/cases")
    cases = cases_response.get("cases", []) if isinstance(cases_response, dict) else []
        
    case_options = {c["id"]: f"{c.get('case_number', '')} - {c.get('title', '')}" for c in cases}
    
    # We define layout first to place the selectbox properly, but fetch logic needs the value
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("Analysis Controls")
        
        selected_case_id = st.selectbox(
            "Select Case", 
            options=["global"] + list(case_options.keys()), 
            format_func=lambda x: "Global Master Graph (All Cases)" if x == "global" else case_options.get(x)
        )
    
    # Now fetch entities using the selected case
    entities_data = api_client.get("/api/v1/graph/entities", {"case_id": selected_case_id})
    if not isinstance(entities_data, list):
        entities_data = []
    entity_options = {e["id"]: f"{e.get('label', 'Unknown')} ({e.get('type', 'Unknown')})" for e in entities_data}
    
    with col1:
        analysis_type = st.selectbox(
            "Analysis Type",
            ["Full Network", "Syndicate Detection", "Path Finder"]
        )
        
        if analysis_type == "Full Network":
            st.info("Visualizes the entire network for the selected case.")
            expand_master = False
            if selected_case_id != "global":
                expand_master = st.checkbox("Load Connections from Master Graph", help="Expands the case graph to include connections spanning to other cases in the entire database.")
                
            if st.button("Generate Case Network", use_container_width=True):
                with st.spinner("Loading case network..."):
                    try:
                        network_data = api_client.get(f"/api/v1/graph/case/{selected_case_id}", {"expand_master": expand_master})
                        st.session_state.network_data = network_data
                    except Exception as e:
                        st.error(f"Error loading case network: {e}")
                
        elif analysis_type == "Syndicate Detection":
            min_connections = st.slider("Min Connections", 2, 10, 3)
            
            if st.button("Detect Syndicates", use_container_width=True):
                _detect_syndicates(min_connections, selected_case_id)
        
        elif analysis_type == "Path Finder":
            if not entity_options or len(entity_options) < 2:
                st.info("Need at least 2 entities to find a path.")
                source = None
                target = None
            else:
                source = st.selectbox(
                    "Source Entity",
                    options=list(entity_options.keys()),
                    format_func=lambda x: entity_options.get(x)
                )
                target = st.selectbox(
                    "Target Entity",
                    options=list(entity_options.keys()),
                    format_func=lambda x: entity_options.get(x),
                    index=1 if len(entity_options) > 1 else 0
                )
            
            if st.button("Find Path", use_container_width=True, disabled=not (source and target)):
                _find_path(source, target, selected_case_id)
        
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
            _render_graph(st.session_state.network_data)
        else:
            st.info("Generate an analysis to see results")
        
        # Syndicate results
        if analysis_type == "Syndicate Detection" and "syndicates" in st.session_state and st.session_state.syndicates:
            _render_syndicates(st.session_state.syndicates)


def _load_network(entity_id: str, depth: int, case_id: str):
    """Load network data from API"""
    if not entity_id:
        st.error("Please enter an entity ID or name")
        return
    
    params = {"depth": depth}
    if case_id != "global":
        params["case_id"] = case_id
        
    result = api_client.get(f"/api/v1/graph/network/{entity_id}", params, timeout=120)
    
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



def _detect_syndicates(min_connections: int, case_id: str):
    """Detect criminal syndicates"""
    params = {"min_connections": min_connections}
    url = "/api/v1/graph/syndicates"
    if case_id != "global":
        url += f"?case_id={case_id}"
        
    result = api_client.post(url, params)
    
    if "error" in result:
        st.error("Failed to detect syndicates")
        return
    
    st.session_state.syndicates = result.get("syndicates", [])


def _find_path(source: str, target: str, case_id: str):
    """Find shortest path between two entities"""
    if not source or not target:
        st.error("Please enter both source and target entity IDs")
        return
    
    url = "/api/v1/graph/path"
    if case_id != "global":
        url += f"?case_id={case_id}"
        
    result = api_client.post(url, {
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
        
        # Try to extract URL from properties
        url = ""
        try:
            import ast
            props_str = node.get("title", "{}")
            props = ast.literal_eval(props_str)
            if isinstance(props, dict):
                url = props.get("url", props.get("profile_url", props.get("link", props.get("source", ""))))
        except:
            pass
            
        net.add_node(
            node["id"],
            label=node.get("label", node["id"]),
            title=node.get("title", ""),
            color=color,
            size=node_size,
            url=url,
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
        
    # Inject JavaScript for enterprise OSINT graph interactions
    click_js = r"""
    var highlightActive = false;
    
    function updateInfoBox(node) {
        var box = document.getElementById("osint-info-box");
        if (!box) {
            box = document.createElement("div");
            box.id = "osint-info-box";
            box.style.position = "absolute";
            box.style.top = "20px";
            box.style.right = "20px";
            box.style.width = "320px";
            box.style.backgroundColor = "rgba(15, 23, 42, 0.95)";
            box.style.color = "#f8fafc";
            box.style.padding = "20px";
            box.style.borderRadius = "12px";
            box.style.boxShadow = "0 15px 25px -5px rgba(0,0,0,0.6)";
            box.style.fontFamily = "system-ui, -apple-system, sans-serif";
            box.style.fontSize = "14px";
            box.style.zIndex = "1000";
            box.style.border = "1px solid #334155";
            box.style.maxHeight = "80%";
            box.style.overflowY = "auto";
            document.getElementById("mynetwork").appendChild(box);
        }
        
        var html = "<h3 style='margin-top:0; margin-bottom:15px; color:#38bdf8; border-bottom:1px solid #334155; padding-bottom:10px;'>" + (node.label || "Entity") + "</h3>";
        
        var linkUrl = "";
        if (node.url) {
            linkUrl = node.url;
        } else if (node.title && typeof node.title === 'string') {
            var match = node.title.match(/https?:\/\/[^\s'"]+/);
            if (match) linkUrl = match[0];
        }
        
        if (linkUrl) {
            html += "<a href='" + linkUrl + "' target='_blank' style='display:inline-block; margin-bottom:15px; padding:8px 12px; background-color:#0ea5e9; color:white; text-decoration:none; border-radius:6px; font-weight:bold; box-shadow:0 4px 6px -1px rgba(0,0,0,0.3);'>🔗 Open Source Link</a>";
        }
        
        if (node.title && typeof node.title === 'string') {
            var cleanTitle = node.title.replace(/[{}]/g, '').replace(/'/g, '');
            var pairs = cleanTitle.split(', ');
            var propsHtml = "<div style='display:flex; flex-direction:column; gap:10px;'>";
            for (var i=0; i<pairs.length; i++) {
                var p = pairs[i].split(': ');
                if (p.length === 2) {
                    var k = p[0].trim();
                    var v = p[1].trim();
                    if (v.startsWith('http')) {
                        v = "<a href='" + v + "' target='_blank' style='color:#38bdf8; word-break:break-all;'>" + v + "</a>";
                    } else {
                        v = "<span style='word-break:break-all;'>" + v + "</span>";
                    }
                    propsHtml += "<div><strong style='color:#94a3b8; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;'>" + k + "</strong><br/>" + v + "</div>";
                } else {
                    propsHtml += "<div style='color:#cbd5e1;'>" + pairs[i] + "</div>";
                }
            }
            propsHtml += "</div>";
            html += propsHtml;
        }
        
        box.innerHTML = html;
        box.style.display = "block";
    }

    network.on("click", function (params) {
        if (params.nodes.length > 0) {
            highlightActive = true;
            var selectedNode = params.nodes[0];
            var connectedNodes = network.getConnectedNodes(selectedNode);
            var allNodesArray = nodes.get();
            var nodeUpdates = [];
            
            for (var i = 0; i < allNodesArray.length; i++) {
                var n = allNodesArray[i];
                if (n.id === selectedNode || connectedNodes.includes(n.id)) {
                    nodeUpdates.push({id: n.id, color: nodeColors[n.id] || n.color});
                } else {
                    nodeUpdates.push({id: n.id, color: 'rgba(200,200,200,0.1)'});
                }
            }
            nodes.update(nodeUpdates);
            
            var connectedEdges = network.getConnectedEdges(selectedNode);
            var allEdgesArray = edges.get();
            var edgeUpdates = [];
            for (var i = 0; i < allEdgesArray.length; i++) {
                var e = allEdgesArray[i];
                if (connectedEdges.includes(e.id)) {
                    edgeUpdates.push({id: e.id, color: {color: '#9ca3af', opacity: 1.0}});
                } else {
                    edgeUpdates.push({id: e.id, color: {color: '#4b5563', opacity: 0.1}});
                }
            }
            edges.update(edgeUpdates);

            updateInfoBox(nodes.get(selectedNode));
            
        } else {
            if (highlightActive) {
                var allNodesArray = nodes.get();
                var nodeUpdates = [];
                for (var i = 0; i < allNodesArray.length; i++) {
                    nodeUpdates.push({id: allNodesArray[i].id, color: nodeColors[allNodesArray[i].id] || allNodesArray[i].color});
                }
                nodes.update(nodeUpdates);
                
                var allEdgesArray = edges.get();
                var edgeUpdates = [];
                for (var i = 0; i < allEdgesArray.length; i++) {
                    edgeUpdates.push({id: allEdgesArray[i].id, color: {color: '#4b5563', opacity: 1.0}});
                }
                edges.update(edgeUpdates);
                
                highlightActive = false;
            }
            var box = document.getElementById("osint-info-box");
            if (box) box.style.display = "none";
        }
    });
    """
    html = html.replace('network = new vis.Network(container, data, options);', 
                        'network = new vis.Network(container, data, options);\n' + click_js)
                        
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