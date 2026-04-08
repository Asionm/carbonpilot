"""
Workflow Relationship Enhancement Module
========================================

This module analyzes sequential relationships between sub-item works within
a specialty subdivision using LLM-based reasoning.

Ontology (Engineering domain):

  sub_division
      CONTAINS →
  specialty_subdivision
      CONTAINS →
  sub_item_work
      CONSUMES →
  resource_item

Note:
- Engineering hierarchy uses CONTAINS (child -> parent).
- BELONGS_TO is only used for generic classes (Time, Region, Source) and is
  not used in this module.
"""

from typing import Dict, List, Union
import sys
import json
import re

from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper
from prompts import WORKFLOW_SEQUENCE_ANALYSIS_PROMPT


# ==========================================================
# 1. Fetch sub-item works under a specialty subdivision
# ==========================================================
def get_specialty_subdivision_works(
    neo4j_wrapper: Neo4jWrapper,
    specialty_subdivision_id: str
) -> List[Dict[str, str]]:
    """
    Fetch all sub_item_work nodes that belong to a given specialty_subdivision.

    In the current ontology:
        (sub_item_work)-[:CONTAINS]->(specialty_subdivision)

    Args:
        neo4j_wrapper: Neo4jWrapper instance
        specialty_subdivision_id: ID of the specialty_subdivision node

    Returns:
        List of dicts: [{"name": ..., "id": ...}, ...]
    """

    query = """
    MATCH (n:sub_item_work)-[:CONTAINS]->(p:specialty_subdivision {id: $parentId})
    RETURN n.name AS name, n.id AS id
    ORDER BY n.name
    """

    result = neo4j_wrapper.execute_query(query, {"parentId": specialty_subdivision_id})

    seen_ids = set()
    unique_works = []
    for record in result:
        if record["id"] not in seen_ids:
            seen_ids.add(record["id"])
            unique_works.append({"name": record["name"], "id": record["id"]})

    return unique_works


# ==========================================================
# 2. LLM-based workflow sequence reasoning
# ==========================================================
def analyze_workflow_sequence(
    llm_wrapper: LLMWrapper,
    subdivision_name: str,
    works: List[Dict[str, str]]
) -> List[Union[str, List[str]]]:
    """
    Analyze the workflow sequence of sub-item works using an LLM.

    Args:
        llm_wrapper: LLMWrapper instance
        subdivision_name: Name of the specialty subdivision
        works: List of {"name": ..., "id": ...}

    Returns:
        A sequence where each element is either:
          - a string ID: "SI-1-1", or
          - a list of IDs: ["SI-1-2", "SI-1-3"] meaning parallel works
    """

    # Map from work name to ID (for LLM outputs that might use names)
    name_to_id = {w["name"]: w["id"] for w in works}
    # Human-readable list for the prompt
    works_list = [f"{w['name']} (ID: {w['id']})" for w in works]

    prompt = WORKFLOW_SEQUENCE_ANALYSIS_PROMPT.format(
        subdivision_name=subdivision_name,
        works_list="\n".join(f"- {w}" for w in works_list)
    )

    try:
        response = llm_wrapper.generate_response(prompt)
        cleaned = response.strip()

        # Try to extract a JSON-like array from the response
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

        sequence = json.loads(cleaned)

        # Normalize sequence to IDs
        validated: List[Union[str, List[str]]] = []
        for item in sequence:
            if isinstance(item, list):
                # Parallel group
                ids = []
                for x in item:
                    x_str = str(x)
                    ids.append(name_to_id.get(x_str, x_str))
                validated.append(ids)
            else:
                x_str = str(item)
                validated.append(name_to_id.get(x_str, x_str))

        return validated

    except Exception as e:
        print(f"Error parsing LLM response: {e}")
        print("Raw response:", response)
        return []


# ==========================================================
# 3. Create PRECEDES relationships
# ==========================================================
def create_precedes_relationships(
    neo4j_wrapper: Neo4jWrapper,
    subdivision_id: str,
    sequence: List[Union[str, List[str]]]
) -> None:
    """
    Create PRECEDES relationships for sub_item_work inside a single
    specialty_subdivision, based on a given sequence.

    We only operate within the given specialty_subdivision, determined by:

        (si:sub_item_work)-[:CONTAINS]->(:specialty_subdivision {id: $sid})
    """

    # 1) Delete existing PRECEDES relationships within this subdivision
    delete_query = """
    MATCH (n:sub_item_work)-[:CONTAINS]->(:specialty_subdivision {id: $sid})
    OPTIONAL MATCH (n)-[r:PRECEDES]->()
    OPTIONAL MATCH (n)<-[r2:PRECEDES]-()
    WITH collect(r) + collect(r2) AS rels
    UNWIND rels AS rel
    DELETE rel
    RETURN count(rel) AS deleted
    """

    delete_result = neo4j_wrapper.execute_query(delete_query, {"sid": subdivision_id})
    deleted_count = delete_result[0]["deleted"] if delete_result else 0
    print(f"  Deleted {deleted_count} PRECEDES relationships in subdivision {subdivision_id}")

    # 2) Create new PRECEDES relationships based on the sequence
    created_count = 0

    for i in range(len(sequence) - 1):
        current_item = sequence[i]
        next_item = sequence[i + 1]

        current_ids = current_item if isinstance(current_item, list) else [current_item]
        next_ids = next_item if isinstance(next_item, list) else [next_item]

        for cur_id in current_ids:
            for nxt_id in next_ids:
                if not cur_id or not nxt_id:
                    continue

                create_query = """
                MATCH (a:sub_item_work {id: $predecessorId})
                MATCH (b:sub_item_work {id: $successorId})
                MERGE (a)-[:PRECEDES]->(b)
                RETURN 1 AS ok
                """

                try:
                    neo4j_wrapper.execute_query(
                        create_query,
                        {"predecessorId": cur_id, "successorId": nxt_id}
                    )
                    created_count += 1
                except Exception as e:
                    print(f"  Error creating PRECEDES {cur_id} -> {nxt_id}: {e}")

    print(f"  Created {created_count} PRECEDES relationships in subdivision {subdivision_id}")


# ==========================================================
# 4. Main orchestration
# ==========================================================
def enhance_relationships(
    neo4j_wrapper: Neo4jWrapper,
    llm_wrapper: LLMWrapper,
    specialty_subdivisions: Dict[str, str]
) -> Dict[str, List[Union[str, List[str]]]]:
    """
    Enhance workflow relationships for all given specialty_subdivision nodes.

    Args:
        neo4j_wrapper: Neo4jWrapper instance
        llm_wrapper: LLMWrapper instance
        specialty_subdivisions: {name: id} mapping

    Returns:
        {subdivision_name: workflow_sequence}
    """

    results: Dict[str, List[Union[str, List[str]]]] = {}

    for subdivision_name, subdivision_id in specialty_subdivisions.items():
        print(f"\n>>> Processing specialty_subdivision: {subdivision_name} ({subdivision_id})")

        works = get_specialty_subdivision_works(neo4j_wrapper, subdivision_id)
        print(f"  Found {len(works)} sub_item_work")

        if len(works) <= 1:
            print("  Not enough sub-item works, skipping.")
            results[subdivision_name] = []
            continue

        if len(works) > 50:
            print("  Too many sub-item works, truncating to first 50.")
            works = works[:50]

        sequence = analyze_workflow_sequence(llm_wrapper, subdivision_name, works)
        print(f"  Workflow sequence: {sequence}")

        results[subdivision_name] = sequence

        if sequence:
            create_precedes_relationships(neo4j_wrapper, subdivision_id, sequence)
        else:
            print("  No sequence produced, skipping PRECEDES creation.")

    return results


# ==========================================================
# 5. CLI entry point
# ==========================================================
def engineering_relationships_enhancement() -> None:
    print("Initializing Neo4j and LLM wrappers...")
    neo4j_wrapper = Neo4jWrapper()
    llm_wrapper = LLMWrapper()

    # Fetch all specialty_subdivision nodes
    print("Fetching specialty_subdivision nodes from Neo4j...")
    query = """
    MATCH (n:specialty_subdivision)
    RETURN n.name AS name, n.id AS id
    """
    rows = neo4j_wrapper.execute_query(query)
    specialty_subdivisions = {r["name"]: r["id"] for r in rows}

    if not specialty_subdivisions:
        print("No specialty_subdivision nodes found.")
        neo4j_wrapper.close()
        sys.exit(1)

    print(f"Found {len(specialty_subdivisions)} specialty_subdivision nodes.")

    print("Analyzing workflow relationships...")
    results = enhance_relationships(neo4j_wrapper, llm_wrapper, specialty_subdivisions)

    print("\n=== Final Workflow Sequences ===")
    for name, seq in results.items():
        print(f"- {name}: {seq}")

    neo4j_wrapper.close()
    print("Done.")
