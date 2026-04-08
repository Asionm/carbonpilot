
import os
from neo4j import GraphDatabase
from langchain_ollama import OllamaEmbeddings
import numpy as np
from typing import List, Dict, Any, Optional

NODE_TYPES = {
    "sub_divisional_work": "sub_divisional_work",
    "specialty_subdivision": "specialty_subdivision",
    "sub_item_work": "sub_item_work",
    "resource_item": "resource_item"
}


CN_NAME_MAP = {v: k for k, v in NODE_TYPES.items()}


def check_vector_index_exists(driver, index_name: str) -> bool:
    query = """
    SHOW VECTOR INDEXES
    YIELD name
    WHERE name = $indexName
    RETURN count(*) > 0 AS exists
    """
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(query, indexName=index_name)
        record = result.single()
        return record["exists"] if record else False

def get_node_key_property(properties: Dict, labels: List[str]) -> str:

    for label in labels:
        if label == "sub_divisional_work":
            return properties.get("name", "N/A")

        elif label == "specialty_subdivision":
            return properties.get("name", "N/A")

        elif label == "sub_item_work":
            return properties.get("name", "N/A")
        elif label == "resource_item":
            return properties.get("name", "N/A")
    return "unknown"


def prune_props(props: Dict[str, Any], max_value_len: int = 256) -> Dict[str, Any]:

        cleaned = {}
        for k, v in (props or {}).items():
            if k in {"embedding", "created_at"} or v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                val = v
                if isinstance(val, str) and len(val) > max_value_len:
                    val = val[:max_value_len] + "…"
                cleaned[k] = val
            else:
                s = str(v)
                cleaned[k] = (s[:max_value_len] + "…") if len(s) > max_value_len else s
        return cleaned

def global_semantic_search(
    driver, 
    query_text: str, 
    top_k: int = 5,
    exclude_labels: List[str] = None
) -> List[Dict[str, Any]]:

    embeddings = OllamaEmbeddings(
        model=os.getenv("EMBEDDING_MODEL"),
        base_url=os.getenv("OLLAMA_BASE_URL"),
        temperature=0.01
    )
    
    query_vector = embeddings.embed_query(query_text)
    

    exclude_condition = ""
    if exclude_labels:

        exclude_labels_str = "[" + ",".join([f"'{label}'" for label in exclude_labels]) + "]"
        exclude_condition = f"AND NONE(label IN labels(n) WHERE label IN {exclude_labels_str})"
    
    query = f"""
    MATCH (n)
    WHERE n.{os.getenv("VECTOR_PROPERTY")} IS NOT NULL
    {exclude_condition}
    WITH n, vector.similarity.cosine($queryVector, n.{os.getenv("VECTOR_PROPERTY")}) AS similarity
    ORDER BY similarity DESC
    LIMIT $topK
    RETURN 
        labels(n) AS labels,
        properties(n) AS properties,
        similarity
    """
    
    with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
        result = session.run(
            query,
            queryVector=query_vector,
            topK=top_k
        )
        return [{
            "labels": record["labels"],
            "properties": prune_props(record["properties"]),
            "similarity": record["similarity"]
        } for record in result]


def local_semantic_search(
    driver, 
    node_type: str, 
    query_text: str, 
    top_k: int = 5,
    parent_node_id: str = None
) -> List[Dict[str, Any]]:

    vector_property = os.getenv("VECTOR_PROPERTY") or "embedding"
    index_name = f"vec_index_{node_type}"
    db_name = os.getenv("NEO4J_DATABASE") or "neo4j"

    embeddings = OllamaEmbeddings(
        model=os.getenv("EMBEDDING_MODEL") or "nomic-embed-text",
        base_url=os.getenv("OLLAMA_BASE_URL"),
    )
    query_vector = embeddings.embed_query(query_text)

    index_exists = check_vector_index_exists(driver, index_name)

    params: Dict[str, Any] = {
        "topK": top_k,
        "queryVector": query_vector,
    }
    if parent_node_id:
        params["parentId"] = parent_node_id

    if parent_node_id:
        if index_exists:
            params.update({"indexName": index_name, "k": max(top_k * 5, top_k)})
            query = f"""
            CALL db.index.vector.queryNodes($indexName, $k, $queryVector)
            YIELD node, score
            WHERE "{node_type}" IN labels(node) AND node.{vector_property} IS NOT NULL
            MATCH (node)-[:CONTAINS*0..5]->(p {{id: $parentId}})
            RETURN labels(node) AS labels,
                   properties(node) AS properties,
                   score AS similarity
            ORDER BY similarity DESC
            LIMIT $topK
            """
        else:
            query = f"""
            MATCH (n:{node_type})-[:CONTAINS*0..5]->(p {{id: $parentId}})
            WHERE n.{vector_property} IS NOT NULL
            WITH n, vector.similarity.cosine($queryVector, n.{vector_property}) AS similarity
            RETURN labels(n) AS labels,
                   properties(n) AS properties,
                   similarity
            ORDER BY similarity DESC
            LIMIT $topK
            """
    else:
        if index_exists:
            params.update({"indexName": index_name})
            query = f"""
            CALL db.index.vector.queryNodes($indexName, $topK, $queryVector)
            YIELD node, score
            WHERE "{node_type}" IN labels(node) AND node.{vector_property} IS NOT NULL
            RETURN labels(node) AS labels,
                   properties(node) AS properties,
                   score AS similarity
            ORDER BY similarity DESC
            LIMIT $topK
            """
        else:
            query = f"""
            MATCH (n:{node_type})
            WHERE n.{vector_property} IS NOT NULL
            WITH n, vector.similarity.cosine($queryVector, n.{vector_property}) AS similarity
            RETURN labels(n) AS labels,
                   properties(n) AS properties,
                   similarity
            ORDER BY similarity DESC
            LIMIT $topK
            """

    with driver.session(database=db_name) as session:
        result = session.run(query, **params)
        return [{
            "labels": record["labels"],
            "properties": prune_props(record["properties"]),
            "similarity": record["similarity"]
        } for record in result]

def get_resource_items(driver, sub_item_work_node: Dict[str, Any], project_info: str="") -> List[Dict[str, Any]]:
    node_id = sub_item_work_node.get("properties", {}).get("id")
    if not node_id:
        return []
    

    resource_blacklist = ["RI-Material-974899ef025c", "RI-Material-eab619fba24a", "RI-Material-36f698265032", 
                             "RI-Material-d0df03650533", "RI-Material-d303ebcee171"]
    
    query = """
    MATCH (si:sub_item_work {id: $id})-[r:CONSUMES]->(ri:resource_item)
    RETURN ri.id AS resource_id, ri.name AS resource_name, ri.category AS category, ri.unit AS unit, r.value AS value
    """
    with driver.session() as session:
        result = session.run(query, id=node_id)
        resources = []
        for record in result:
            resource_id = record['resource_id']
            # 排除黑名单中的资源项
            if resource_id not in resource_blacklist:
                resources.append({
                    'resource_id': resource_id,
                    'resource_name': record['resource_name'],
                    'category': record['category'],
                    'unit': record['unit'],
                    'value': record['value']
                })
        if project_info:
            from configs.llm_wrapper import LLMWrapper
            llm_wrapper = LLMWrapper()
            
            # Prepare the prompt for LLM to correct resource names
            resource_descriptions = []
            for resource in resources:
                resource_descriptions.append(f"ID: {resource['resource_id']}, Name: {resource['resource_name']}, Category: {resource['category']}")
            
            resource_list_str = "\n".join(resource_descriptions)
            
            prompt = f"""
Based on the project information, please correct the resource names if needed. 
Only correct the names when there's a clear conflict between the resource name and project information.
For example, if the project specifies C30 concrete but the resource is named C20 concrete, correct it to C30.

Project Information: {project_info}

Resources:
{resource_list_str}

Return a JSON object with corrected names in the format:
{{
    "corrections": [
        {{"id": "resource_id", "corrected_name": "new_name"}},
        ...
    ]
}}

If no corrections are needed, return an empty corrections array.
"""

            try:
                response = llm_wrapper.generate_response(prompt)
                # Try to parse the JSON response
                import json
                import re
                
                # Extract JSON from the response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    response_json = json.loads(json_match.group())
                    corrections = response_json.get('corrections', [])
                    
                    # Apply corrections
                    id_to_corrected_name = {corr['id']: corr['corrected_name'] for corr in corrections}
                    for resource in resources:
                        if resource['resource_id'] in id_to_corrected_name:
                            resource['resource_name'] = id_to_corrected_name[resource['resource_id']]
            except Exception as e:
                # If anything fails, we just continue with original names
                pass
                
        return resources
    

def find_item_by_id(search_results: List[Dict[str, Any]], target_id: str) -> Optional[Dict[str, Any]]:

    for item in search_results:
        properties = item.get("properties", {})
        if properties.get("id") == target_id:
            return item
    return None


def get_precedes_family(driver, quota_id: str) -> List[Dict[str, Any]]:

    query = """
    MATCH (q:sub_item_work {id: $quotaId})
    OPTIONAL MATCH (q)-[:PRECEDES]->(descendant:sub_item_work)
    OPTIONAL MATCH (ancestor:sub_item_work)-[:PRECEDES]->(q)
    OPTIONAL MATCH (sibling:sub_item_work)-[:PRECEDES]->(common_ancestor:sub_item_work)<-[:PRECEDES]-(q)
    WHERE sibling <> q
    OPTIONAL MATCH (q)-[:PRECEDES]->(common_ancestor2:sub_item_work)<-[:PRECEDES]-(sibling2:sub_item_work)
    WHERE sibling2 <> q
    WITH collect(descendant) + collect(ancestor) + collect(sibling) + collect(sibling2) AS related_nodes
    UNWIND related_nodes AS node
    RETURN DISTINCT node.id AS id, node.name AS name
    """
    
    with driver.session() as session:
        result = session.run(query, quotaId=quota_id)
        return [{"id": record["id"], "name": record["name"]} for record in result]


def get_precedes_family_with_relationships(driver, quota_id: str) -> Dict[str, Any]:
    query = """
    MATCH (q:sub_item_work {id: $quotaId})
    WITH q,
         [(q)-[:PRECEDES]->(d) | d] +
         [(a)-[:PRECEDES]->(q) | a] +
         [(q)-[:PRECEDES]->()<-[:PRECEDES]-(s) WHERE s <> q | s] +
         [q] AS rawNodes
    UNWIND rawNodes AS n
    WITH collect(DISTINCT n) AS nodes
    RETURN
      [n IN nodes | {id: n.id, name: n.name, unit: coalesce(n.unit, "")}] AS members,
      reduce(rels = [],
             src IN nodes |
             rels + [(src)-[:PRECEDES]->(t) WHERE t IN nodes |
                       {source: {id: src.id, name: src.name, unit: coalesce(src.unit, "")},
                        target: {id: t.id, name: t.name, unit: coalesce(t.unit, "")}}]
      ) AS relationships
    """
    with driver.session() as session:
        record = session.run(query, quotaId=quota_id).single()
        return {
            "members": record["members"],
            "relationships": record["relationships"],
        }