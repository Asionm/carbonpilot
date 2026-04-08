# -*- coding: utf-8 -*-
"""
Neo4j Engineering-Carbon Knowledge Graph Vectorization Tool
===========================================================

This script performs semantic vectorization over the engineered knowledge graph.
It supports:

1. Semantic description generation (LLM-based)
2. Embedding generation using Ollama BGE models
3. Writing embeddings back to Neo4j
4. Writing improved semantic intro back to Neo4j
5. Incremental or forced recomputation
6. Batch-based vectorization
7. Multiple node types (strict ontology structure)

Ontology node types:
- sub_division
- specialty_subdivision
- sub_item_work
- resource_item
- Time
- Region
- Source

For each node:
    description = LLM(name + intro)
    intro := description
    embedding := vectorize(description)

Requirements:
- Neo4j 5.x
- Ollama running
- BGE model available (e.g., bge-m3)
"""

import os
import time
from typing import Dict, List, Any, Iterable

from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_community.embeddings import OllamaEmbeddings
from tqdm import tqdm

from configs.llm_wrapper import LLMWrapper
from prompts import SEMANTIC_BRIEF_PROMPT


# ============================================================
# Load environment
# ============================================================
load_dotenv(".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
EMBED_MODEL = os.getenv("EMBEDDING_MODEL")

BATCH_SIZE = 20
VECTOR_PROPERTY = "embedding"
RECOMPUTE_EXISTING = False

SELECTED_NODE_TYPES: List[str] = []
FORCE_RECOMPUTE_TYPES: List[str] = ["resource_item"]

# Global flag for semantic enhancement
ENABLE_SEMANTIC_ENHANCEMENT = True


# ============================================================
# Node type configuration (strict ontology)
# ============================================================
NODE_TYPES_CONFIG = {
    "sub_division": {
        "label": "Sub-Division",
        "text_fields": ["name", "intro"],
        "prefix": "Sub-Division: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "specialty_subdivision": {
        "label": "Specialty Subdivision",
        "text_fields": ["name", "intro"],
        "prefix": "Specialty Subdivision: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "sub_item_work": {
        "label": "Sub-Item Work",
        "text_fields": ["name", "unit", "intro"],
        "prefix": "Sub-Item Work: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "resource_item": {
        "label": "Resource Item",
        "text_fields": ["name", "category", "unit", "intro"],
        "prefix": "Resource Item: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Time": {
        "label": "Time",
        "text_fields": ["name", "intro"],
        "prefix": "Time: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Region": {
        "label": "Region",
        "text_fields": ["name", "intro"],
        "prefix": "Region: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Source": {
        "label": "Source",
        "text_fields": ["name", "intro"],
        "prefix": "Source: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    }
}


# ============================================================
# Node Type Normalization Helpers
# ============================================================
def _normalize_types(types: Iterable[str]) -> List[str]:
    if not types:
        return []
    items = [t.strip() for t in types if t and t.strip()]
    unknown = [t for t in items if t not in NODE_TYPES_CONFIG]
    if unknown:
        raise ValueError(f"Unknown node types: {unknown}. Valid types: {list(NODE_TYPES_CONFIG.keys())}")
    return items


def _iter_target_types(selected: List[str]) -> List[str]:
    return selected if selected else list(NODE_TYPES_CONFIG.keys())


# ============================================================
# Core: Semantic Description Builder
# ============================================================
def get_node_text(node: Dict[str, Any], config: Dict[str, Any], llm=None) -> str:
    """
    Build semantic description for the node.
    1. Combine name + intro
    2. Use LLM to generate a refined semantic summary
    3. Write the summary back into node["intro"]
    4. Return final text for embedding
    """
    name = node.get("name", "")
    intro = node.get("intro", "")

    base_text = f"Name: {name}\nIntro: {intro}".strip()

    # Generate improved intro using LLM
    if llm and ENABLE_SEMANTIC_ENHANCEMENT:
        try:
            prompt_msgs = SEMANTIC_BRIEF_PROMPT.format_messages(node_info=base_text)
            prompt_text = "\n".join(
                getattr(m, "content", str(m)) for m in prompt_msgs
            )
            new_intro = llm.generate_response(prompt_text).strip()
            if new_intro:
                intro = new_intro[:200]
        except Exception as e:
            print(f"⚠️ LLM description generation failed: {e}")

    # Update intro for write-back
    node["intro"] = intro

    # Construct embedding text
    parts = []
    for field in config["text_fields"]:
        v = str(node.get(field, "") or "").strip()
        if v:
            parts.append(v)

    combined = " ".join(parts)
    return f"{config['prefix']}{combined}"


# ============================================================
# Batch Processing: Write Intro + Embedding
# ============================================================
def process_batch(tx, nodes: List[Dict[str, Any]], node_type: str,
                  embeddings, vector_property: str, llm):

    config = NODE_TYPES_CONFIG[node_type]

    descriptions = []
    metadata = []

    # Step 1: Build semantic description
    for row in nodes:
        node_props = dict(row["n"])
        element_id = row["elementId"]

        text = get_node_text(node_props, config, llm=llm)
        descriptions.append(text)
        metadata.append((element_id, node_props.get("intro", "")))

    # Step 2: Write updated intro back into Neo4j
    for element_id, intro in metadata:
        tx.run(
            f"MATCH (n:{node_type}) WHERE elementId(n)=$elementId "
            "SET n.intro=$intro",
            elementId=element_id,
            intro=intro
        )

    # Step 3: Generate embeddings
    try:
        vectors = embeddings.embed_documents(descriptions)
    except Exception as e:
        print(f"❌ Embedding generation failed: {e}")
        return 0

    # Step 4: Write vectors back to Neo4j
    for i, (element_id, _) in enumerate(metadata):
        vec = vectors[i]
        tx.run(
            f"MATCH (n:{node_type}) WHERE elementId(n)=$elementId "
            f"SET n.{vector_property} = $vec",
            elementId=element_id,
            vec=vec
        )

    return len(metadata)


# ============================================================
# Main Vectorization Pipeline
# ============================================================
def vectorize_nodes(
    uri: str, username: str, password: str, database: str, embeddings,
    vector_property: str, recompute_existing=False,
    selected_types: List[str] = None, force_types: List[str] = None):

    selected_types = _normalize_types(selected_types or SELECTED_NODE_TYPES)
    force_types = set(_normalize_types(force_types or FORCE_RECOMPUTE_TYPES))

    targets = _iter_target_types(selected_types)
    driver = GraphDatabase.driver(uri, auth=(username, password))
    llm = LLMWrapper()

    print("\n=== Vectorization Pipeline Start ===")

    try:
        with driver.session(database=database) as session:

            # Count total nodes
            total = 0
            for nt in targets:
                config = NODE_TYPES_CONFIG[nt]
                where = config["where_clause"]

                if nt not in force_types and not recompute_existing:
                    where += f" AND size(coalesce(n.{vector_property}, [])) = 0"

                cnt = session.run(
                    f"MATCH (n:{nt}) {where} RETURN count(*) AS c"
                ).single()["c"]
                total += cnt

                mode = "force" if nt in force_types else ("full" if recompute_existing else "missing-only")
                print(f"- {nt}: {cnt} nodes ({mode})")

            if total == 0:
                print("No nodes need vectorization.")
                return

            # Process each type
            processed = 0
            for nt in targets:
                config = NODE_TYPES_CONFIG[nt]
                where = config["where_clause"]

                if nt not in force_types and not recompute_existing:
                    where += f" AND size(coalesce(n.{vector_property}, [])) = 0"

                print(f"\nProcessing: {nt}")

                rows = session.run(
                    f"MATCH (n:{nt}) {where} "
                    "RETURN elementId(n) AS elementId, n"
                ).data()

                for i in range(0, len(rows), BATCH_SIZE):
                    batch = rows[i:i+BATCH_SIZE]
                    n = session.execute_write(
                        process_batch, batch, nt, embeddings, vector_property, llm
                    )
                    processed += n
                    print(f"Processed {processed}/{total}")

        print("\n=== Vectorization Completed ===")

    finally:
        driver.close()


# ============================================================
# Index creation
# ============================================================
def create_vector_index(uri, username, password, database, vector_property, dim=4096):
    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        with driver.session(database=database) as session:
            for nt in NODE_TYPES_CONFIG.keys():
                index_name = f"vec_index_{nt}"
                try:
                    session.run(
                        f"CREATE VECTOR INDEX {index_name} IF NOT EXISTS "
                        f"FOR (n:{nt}) ON (n.{vector_property}) "
                        f"OPTIONS {{indexConfig: {{`vector.dimensions`: {dim}, "
                        f"`vector.similarity_function`: 'cosine'}}}}"
                    )
                    print(f"Vector index created: {index_name}")
                except Exception as e:
                    print(f"Index creation failed for {nt}: {e}")
    finally:
        driver.close()


# ============================================================
# Public Entry Function
# ============================================================
def quota_vectorize(enhance_semantic=True):
    global ENABLE_SEMANTIC_ENHANCEMENT
    ENABLE_SEMANTIC_ENHANCEMENT = enhance_semantic
    print(f"\n===== Engineering-Carbon KG Vectorization =====")
    print(f"Semantic enhancement: {'Enabled' if ENABLE_SEMANTIC_ENHANCEMENT else 'Disabled'}")

    # Check Ollama service
    try:
        import requests
        if requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).status_code == 200:
            print("Ollama service OK.")
    except:
        print("❌ Cannot reach Ollama service.")
        return

    # Init embeddings
    print(f"Loading embedding model: {EMBED_MODEL}")
    try:
        embeddings = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.01
        )
        test = embeddings.embed_query("test")
        print(f"Embedding model loaded. Dimension={len(test)}")
    except Exception as e:
        print("Embedding model load failed:", e)
        return

    # Vectorize
    vectorize_nodes(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
        embeddings=embeddings,
        vector_property=VECTOR_PROPERTY,
        recompute_existing=RECOMPUTE_EXISTING,
        selected_types=SELECTED_NODE_TYPES,
        force_types=FORCE_RECOMPUTE_TYPES
    )

    # Index
    create_vector_index(
        uri=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
        vector_property=VECTOR_PROPERTY,
        dim=4096
    )

    print("\n===== All Done =====")
