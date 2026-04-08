from typing import List, Dict, Any, Optional
from neo4j import Driver


def get_connected_nodes_by_id(
    driver: Driver, 
    node_id: str, 
    relationship_type: Optional[str] = None,
    direction: str = "BOTH"
) -> List[Dict[str, Any]]:


    if relationship_type:
        rel_pattern = f"-[r:{relationship_type}]-"
    else:
        rel_pattern = "-[r]-"
    
    if direction == "IN":
        rel_pattern = f"<{rel_pattern}"
    elif direction == "OUT":
        rel_pattern = f"{rel_pattern}>"

    
    query = f"""
    MATCH (n {{id: $node_id}}){rel_pattern}(connected)
    RETURN 
        labels(connected) AS labels,
        properties(connected) AS properties,
        type(r) AS relationship_type,
        startNode(r).id AS start_node_id,
        endNode(r).id AS end_node_id
    """
    
    with driver.session() as session:
        result = session.run(query, node_id=node_id)
        connected_nodes = []
        for record in result:
            connected_nodes.append({
                "labels": record["labels"],
                "properties": record["properties"],
                "relationship": {
                    "type": record["relationship_type"],
                    "start_node_id": record["start_node_id"],
                    "end_node_id": record["end_node_id"]
                }
            })
        return connected_nodes


def get_connected_nodes_with_weights(
    driver: Driver, 
    node_id: str,
    relationship_type: Optional[str] = None
) -> List[Dict[str, Any]]:

    # 构建Cypher查询
    if relationship_type:
        rel_pattern = f"-[r:{relationship_type}]-"
    else:
        rel_pattern = "-[r]-"
    
    query = f"""
    MATCH (n {{id: $node_id}}){rel_pattern}(connected)
    RETURN 
        labels(connected) AS labels,
        properties(connected) AS properties,
        type(r) AS relationship_type,
        r.value AS weight,
        r AS relationship_properties
    """
    
    with driver.session() as session:
        result = session.run(query, node_id=node_id)
        connected_nodes = []
        for record in result:
            connected_nodes.append({
                "labels": record["labels"],
                "properties": record["properties"],
                "relationship": {
                    "type": record["relationship_type"],
                    "weight": record["weight"],
                    "properties": dict(record["relationship_properties"]) if record["relationship_properties"] else {}
                }
            })
        return connected_nodes


def get_shortest_path_between_nodes(
    driver: Driver, 
    start_node_id: str, 
    end_node_id: str,
    max_depth: int = 10
) -> List[Dict[str, Any]]:

    query = """
    MATCH path = shortestPath((start {id: $start_node_id})-[*..$max_depth]-(end {id: $end_node_id}))
    UNWIND nodes(path) AS node
    WITH path, node, range(0, size(nodes(path))-1) AS idx_list
    UNWIND idx_list AS idx
    WITH path, node, idx
    WHERE idx < size(nodes(path))
    RETURN 
        idx,
        labels(node) AS labels,
        properties(node) AS properties,
        CASE 
            WHEN idx < size(relationships(path)) THEN relationships(path)[idx]
            ELSE null
        END AS relationship
    ORDER BY idx
    """
    
    with driver.session() as session:
        result = session.run(
            query, 
            start_node_id=start_node_id, 
            end_node_id=end_node_id,
            max_depth=max_depth
        )
        
        path_elements = []
        for record in result:
            element = {
                "index": record["idx"],
                "node": {
                    "labels": record["labels"],
                    "properties": record["properties"]
                }
            }
            
            if record["relationship"]:
                element["relationship"] = {
                    "type": record["relationship"].type,
                    "properties": dict(record["relationship"])
                }
            
            path_elements.append(element)
            
        return path_elements


def get_node_relationship_summary(
    driver: Driver, 
    node_id: str
) -> Dict[str, Any]:

    query = """
    MATCH (n {id: $node_id})
    OPTIONAL MATCH (n)-[outgoing]->()
    OPTIONAL MATCH (n)<-[incoming]-()
    OPTIONAL MATCH (n)-[rels]-(connected)
    RETURN 
        count(DISTINCT outgoing) AS out_degree,
        count(DISTINCT incoming) AS in_degree,
        count(DISTINCT connected) AS connected_nodes_count,
        collect(DISTINCT labels(connected)) AS connected_node_types
    """
    
    with driver.session() as session:
        result = session.run(query, node_id=node_id)
        record = result.single()
        
        if record:
            return {
                "node_id": node_id,
                "out_degree": record["out_degree"],
                "in_degree": record["in_degree"],
                "total_connections": record["connected_nodes_count"],
                "connected_types": record["connected_node_types"]
            }
        else:
            return {
                "node_id": node_id,
                "out_degree": 0,
                "in_degree": 0,
                "total_connections": 0,
                "connected_types": []
            }


def find_nodes_by_relationship_pattern(
    driver: Driver,
    node_id: str,
    pattern: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    match_clause = "MATCH (n {id: $node_id})"
    where_clauses = []
    return_vars = ["labels(result) AS labels", "properties(result) AS properties"]
    
    for i, step in enumerate(pattern):
        direction = step.get("direction", "BOTH")
        rel_type = step.get("relationship_type")
        node_labels = step.get("node_labels")
        
        if rel_type:
            rel_pattern = f"[r{i}:{rel_type}]"
        else:
            rel_pattern = f"[r{i}]"
            
        if direction == "OUT":
            rel_pattern = f"-{rel_pattern}->"
        elif direction == "IN":
            rel_pattern = f"<-{rel_pattern}-"
        else:  # BOTH
            rel_pattern = f"-{rel_pattern}-"
            
        match_clause += f"{rel_pattern}(n{i+1}"
        if node_labels:
            if isinstance(node_labels, str):
                match_clause += f":{node_labels}"
            elif isinstance(node_labels, list):
                match_clause += f":{':'.join(node_labels)}"
        match_clause += ")"
        
        if node_labels:
            var_name = f"n{i+1}"
            if isinstance(node_labels, str):
                where_clauses.append(f"{var_name}:{node_labels}")
            elif isinstance(node_labels, list):
                label_conditions = [f"{var_name}:{label}" for label in node_labels]
                where_clauses.append(" OR ".join(label_conditions))
    

    return_vars[0] = f"labels(n{len(pattern)}) AS labels"
    return_vars[1] = f"properties(n{len(pattern)}) AS properties"
    
    query = f"""
    {match_clause}
    {"WHERE " + " AND ".join(where_clauses) if where_clauses else ""}
    RETURN {", ".join(return_vars)}
    """
    
    with driver.session() as session:
        result = session.run(query, node_id=node_id)
        nodes = []
        for record in result:
            nodes.append({
                "labels": record["labels"],
                "properties": record["properties"]
            })
        return nodes