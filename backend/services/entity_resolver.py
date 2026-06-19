"""
Entity resolution and deduplication
"""
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher


class EntityResolver:
    """
    Resolve and merge duplicate entities
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
    
    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate string similarity"""
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
    
    def resolve_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Group similar entities and merge them
        """
        if not entities:
            return []
        
        clusters = []
        used = set()
        
        for i, entity in enumerate(entities):
            if i in used:
                continue
            
            # Start new cluster
            cluster = [entity]
            used.add(i)
            
            # Find similar entities
            for j, other in enumerate(entities[i+1:], start=i+1):
                if j in used:
                    continue
                
                similarity = self._compare_entities(entity, other)
                if similarity >= self.similarity_threshold:
                    cluster.append(other)
                    used.add(j)
            
            # Merge cluster into single entity
            merged = self._merge_cluster(cluster)
            clusters.append(merged)
        
        return clusters
    
    def _compare_entities(self, e1: Dict, e2: Dict) -> float:
        """Compare two entities for similarity"""
        # Compare by different attributes based on entity type
        type1 = e1.get("entity_type")
        type2 = e2.get("entity_type")
        
        if type1 != type2:
            return 0.0
        
        # Compare by name/username
        name1 = e1.get("properties", {}).get("name", "")
        name2 = e2.get("properties", {}).get("name", "")
        
        if name1 and name2:
            return self.calculate_similarity(name1, name2)
        
        # Compare by other identifiers
        username1 = e1.get("properties", {}).get("username", "")
        username2 = e2.get("properties", {}).get("username", "")
        
        if username1 and username2:
            return self.calculate_similarity(username1, username2)
        
        return 0.0
    
    def _merge_cluster(self, cluster: List[Dict]) -> Dict:
        """Merge a cluster of similar entities"""
        if len(cluster) == 1:
            return cluster[0]
        
        # Start with first entity
        merged = cluster[0].copy()
        
        # Merge properties from others
        for entity in cluster[1:]:
            for key, value in entity.get("properties", {}).items():
                if key not in merged["properties"] or not merged["properties"][key]:
                    merged["properties"][key] = value
                elif isinstance(value, list):
                    # Merge lists
                    existing = merged["properties"].get(key, [])
                    if isinstance(existing, list):
                        merged["properties"][key] = list(set(existing + value))
                    else:
                        merged["properties"][key] = [existing] + value
        
        # Mark as merged
        merged["merged_from"] = [e.get("id") for e in cluster]
        merged["merge_count"] = len(cluster)
        
        return merged