"""
Neo4j graph operations
"""
from typing import List, Dict, Optional, Any
from neo4j import AsyncGraphDatabase
import networkx as nx
import json
import os

from backend.models.graph import EntityNode, Relationship


class CrimeGraphBuilder:
    """
    Neo4j graph database operations
    """
    
    def __init__(self, driver: AsyncGraphDatabase):
        self.driver = driver
            
    async def create_entity(self, entity: EntityNode) -> str:
        """
        Create or merge an entity node
        """
        import uuid
        
        props = entity.properties.copy()
        props['node_type'] = entity.node_type
        
        if not entity.node_id:
            entity.node_id = str(uuid.uuid4())
        props['id'] = entity.node_id
        
        # Build Cypher query dynamically
        prop_keys = ', '.join([f"{k}: ${k}" for k in props.keys()])
        
        query = f"""
        MERGE (n:{entity.node_type} {{id: $id}})
        SET n += {{{prop_keys}}}
        RETURN n.id as node_id
        """
        
        async with self.driver.session() as session:
            result = await session.run(query, **props)
            record = await result.single()
            return record["node_id"]
            
    async def delete_entity(self, entity_id: str) -> bool:
        """
        Delete an entity node and all its relationships by ID
        """
        async with self.driver.session() as session:
            query = """
            MATCH (n {id: $id})
            DETACH DELETE n
            """
            result = await session.run(query, id=entity_id)
            summary = await result.consume()
            return summary.counters.nodes_deleted > 0
    
    async def create_relationship(self, rel: Relationship) -> bool:
        """
        Create relationship between two nodes
        """
        async with self.driver.session() as session:
            query = f"""
            MATCH (a {{id: $source_id}})
            MATCH (b {{id: $target_id}})
            MERGE (a)-[r:{rel.rel_type}]->(b)
            SET r += $props
            RETURN r
            """
            
            result = await session.run(
                query,
                source_id=rel.source_id,
                target_id=rel.target_id,
                props={
                    **rel.properties,
                    "confidence": rel.confidence,
                    "evidence": rel.evidence,
                    "discovered_at": rel.discovered_at.isoformat()
                }
            )
            return await result.single() is not None
    
    async def find_syndicates(self, min_connections: int = 3) -> List[Dict]:
        """
        Detect criminal syndicates using community detection
        """
        async with self.driver.session() as session:
            # Find tightly connected clusters
            query = """
            MATCH (p)-[:KNOWS|TRANSACTED_WITH|RELATED_TO|HAS_IDENTIFIER*1..3]-(other)
            WHERE (p:Person OR p:DigitalIdentity OR p:Organization) 
              AND (other:Person OR other:DigitalIdentity OR other:Organization)
            WITH p, collect(DISTINCT other) as connections
            WHERE size(connections) >= $min_conn
            RETURN p.id as person_id, 
                   coalesce(p.name, p.username, p.id) as name,
                   size(connections) as connection_count,
                   [x in connections | x.id] as connected_ids
            ORDER BY connection_count DESC
            """
            
            result = await session.run(query, min_conn=min_connections)
            records = []
            async for record in result:
                records.append(dict(record))
            return records
    
    async def get_network_graph(self, center_node_id: str, depth: int = 2) -> Dict:
        """
        Get subgraph for visualization.
        Searches by node id, name, or username so callers can pass either
        a UUID or a human-readable identifier.
        """
        async with self.driver.session() as session:
            # neo4j 5.x: use startNode(r)/endNode(r) in Cypher instead of
            # rel.start_node / rel.end_node which are unavailable on query results.
            # Also match by id OR name OR username so the UI can pass a name.
            query = f"""
            MATCH (center)
            WHERE center.id = $center_id
               OR toLower(center.name) = toLower($center_id)
               OR toLower(center.username) = toLower($center_id)
               OR toLower(center.email) = toLower($center_id)
               OR center.phone = $center_id
               OR center.upi = $center_id
               OR center.ip = $center_id
               OR center.bank_account = $center_id
               OR toLower(center.domain) = toLower($center_id)
            OPTIONAL MATCH path = (center)-[*1..{depth}]-(connected)
            WITH center,
                 CASE WHEN path IS NULL THEN [] ELSE nodes(path) END AS path_nodes,
                 CASE WHEN path IS NULL THEN [] ELSE relationships(path) END AS path_rels
            UNWIND (path_rels + [null]) AS r
            WITH center, path_nodes,
                 CASE WHEN r IS NULL THEN null
                      ELSE {{start_id: startNode(r).id, end_id: endNode(r).id,
                             rel_type: type(r), props: properties(r)}}
                 END AS edge_data
            RETURN center,
                   path_nodes AS path_nodes,
                   collect(DISTINCT edge_data) AS edge_list
            """

            result = await session.run(query, center_id=center_node_id)
            records = [r async for r in result]

            # If no records, center node was not found - return empty graph
            if not records:
                return {"nodes": [], "edges": []}

            nodes: Dict[str, Any] = {}
            edges: list = []

            for record in records:
                # Add center node
                center = record["center"]
                center_key = center.get("id") or center_node_id
                nodes[center_key] = {
                    "id": center_key,
                    "label": center.get("name") or center.get("username") or center_key,
                    "group": center.get("node_type", "Unknown"),
                    "title": str(dict(center))
                }

                # Add connected nodes
                for node in (record["path_nodes"] or []):
                    node_key = node.get("id")
                    if node_key and node_key not in nodes:
                        nodes[node_key] = {
                            "id": node_key,
                            "label": node.get("name") or node.get("username") or node_key,
                            "group": node.get("node_type", "Unknown"),
                            "title": str(dict(node))
                        }

                # Collect edges from the aggregated edge_list
                for edge_data in (record["edge_list"] or []):
                    if edge_data is None:
                        continue
                    start_id = edge_data["start_id"]
                    end_id = edge_data["end_id"]
                    if start_id and end_id and start_id != end_id:
                        edges.append({
                            "from": start_id,
                            "to": end_id,
                            "label": edge_data["rel_type"],
                            "title": str(dict(edge_data.get("props", {})))
                        })

            # Remove duplicate edges
            seen_edges: set = set()
            unique_edges = []
            for edge in edges:
                edge_key = (edge["from"], edge["to"], edge["label"])
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    unique_edges.append(edge)

            return {
                "nodes": list(nodes.values()),
                "edges": unique_edges
            }
    
    async def shortest_path(self, source_id: str, target_id: str) -> Optional[Dict]:
        """
        Find shortest path between two entities
        """
        async with self.driver.session() as session:
            query = """
            MATCH path = shortestPath(
                (a {id: $source})-[:KNOWS|TRANSACTED_WITH|HAS_IDENTITY*]-(b {id: $target})
            )
            RETURN [node in nodes(path) | {id: node.id, type: node.node_type, name: node.name}] as path_nodes,
                   [rel in relationships(path) | type(rel)] as path_rels,
                   length(path) as path_length
            """
            
            result = await session.run(query, source=source_id, target=target_id)
            record = await result.single()
            
            if record:
                return {
                    "nodes": record["path_nodes"],
                    "relationships": record["path_rels"],
                    "path_length": record["path_length"],
                    "confidence": 1.0
                }
            return None

def build_deterministic_graph(correlation_json: Dict, output_path: str = "output/deterministic_graph.json") -> Dict:
    """
    Takes nodes and edges from the LLM, loads them into NetworkX, 
    automatically merges nodes sharing the exact same identifier, 
    and exports a final merged JSON structure.
    """
    G = nx.Graph()
    
    nodes = correlation_json.get("nodes", [])
    edges = correlation_json.get("edges", [])
    
    # 1. Add all nodes
    for node in nodes:
        node_id = node.get("id")
        if node_id:
            G.add_node(node_id, type=node.get("type"), attributes=node.get("attributes", {}))
            
    # 2. Add edges
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target and G.has_node(source) and G.has_node(target):
            G.add_edge(source, target, relation=edge.get("relation", "LINKED"))
            
    # 3. Deterministic Merge: merge nodes that have the same exact email/phone attributes
    # We will build a mapping of unique_value -> node_id
    identifier_map = {}
    nodes_to_merge = [] # List of tuples (node_id1, node_id2)
    
    for n in G.nodes(data=True):
        node_id = n[0]
        attrs = n[1].get("attributes", {})
        
        # Check attributes that act as hard identifiers
        for key in ["email", "phone", "username"]:
            val = attrs.get(key)
            if val:
                val = str(val).lower().strip()
                dict_key = f"{key}:{val}"
                if dict_key in identifier_map:
                    nodes_to_merge.append((identifier_map[dict_key], node_id))
                else:
                    identifier_map[dict_key] = node_id

    # Execute merges
    for u, v in nodes_to_merge:
        if G.has_node(u) and G.has_node(v) and u != v:
            # Merge attributes first
            attrs_u = G.nodes[u].get("attributes", {})
            attrs_v = G.nodes[v].get("attributes", {})
            for k, val in attrs_v.items():
                if k not in attrs_u or not attrs_u[k]:
                    attrs_u[k] = val
            nx.set_node_attributes(G, {u: {"attributes": attrs_u}})
            
            # Contract nodes
            G = nx.contracted_nodes(G, u, v, self_loops=False)

    # 4. Export JSON
    final_nodes = []
    for n in G.nodes(data=True):
        final_nodes.append({"id": n[0], "type": n[1].get("type"), "attributes": n[1].get("attributes", {})})
        
    final_edges = []
    for u, v, data in G.edges(data=True):
        final_edges.append({"source": u, "target": v, "relation": data.get("relation", "LINKED")})
        
    final_data = {"nodes": final_nodes, "edges": final_edges}
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(final_data, f, indent=2)
        
    return final_data