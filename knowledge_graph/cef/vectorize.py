# -*- coding: utf-8 -*-
"""
Vectorization Pipeline for Carbon Emission Factor Knowledge Graph

Aligned with new ontology:

Engineering domain: (Factor is in carbon domain)
Generic domain labels:
  - Time
  - Region
  - Source

Nodes are vectorized via:
  - LLM short summary (Factor only)
  - Text construction from selected fields
  - BGE embeddings (via Ollama)
"""

import os
import time
from typing import Dict, List, Any, Iterable
from pathlib import Path
import sys

from dotenv import load_dotenv
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from prompts import SEMANTIC_BRIEF_PROMPT
from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper

from langchain_community.embeddings import OllamaEmbeddings
from tqdm import tqdm

load_dotenv(".env")

# ---------------- CONFIG ----------------

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

BATCH_SIZE = 10
VECTOR_PROPERTY = "embedding"
RECOMPUTE_EXISTING = False

SELECTED_NODE_TYPES: List[str] = []
FORCE_RECOMPUTE_TYPES: List[str] = []

# Add a new flag for controlling semantic enhancement
ENABLE_SEMANTIC_ENHANCEMENT = True

# Unified Ontology labels
NODE_TYPES_CONFIG = {
    "Factor": {
        "label": "Carbon Emission Factor",
        "text_fields": ["name", "category", "unit", "intro"],
        "prefix": "Carbon Emission Factor: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Region": {
        "label": "Region",
        "text_fields": ["name", "intro"],
        "prefix": "Region: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Time": {
        "label": "Time Period",
        "text_fields": ["name", "intro"],
        "prefix": "Time: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    },
    "Source": {
        "label": "Source",
        "text_fields": ["name", "intro"],
        "prefix": "Source: ",
        "where_clause": "WHERE n.name IS NOT NULL"
    }
}


# ---------------- Helpers ----------------
def _normalize_types(types: Iterable[str]) -> List[str]:
    if not types:
        return []
    items = [t.strip() for t in types if t and t.strip()]
    unknown = [t for t in items if t not in NODE_TYPES_CONFIG]
    if unknown:
        raise ValueError(f"Unknown node types: {unknown}. Allowed: {list(NODE_TYPES_CONFIG.keys())}")
    return items


def _iter_target_types(selected_types: List[str]) -> List[str]:
    return list(NODE_TYPES_CONFIG.keys()) if not selected_types else selected_types


# ---------------- Text Construction ----------------
def get_node_text(node: Dict[str, Any], config: Dict[str, Any],
                  llm: LLMWrapper = None, node_type: str = "") -> str:

    parts: List[str] = []

    # only Factor uses LLM summary
    if node_type == "Factor" and llm is not None and ENABLE_SEMANTIC_ENHANCEMENT:
        try:
            raw_info = (
                f"Name: {node.get('name','')}, "
                f"Category: {node.get('category','')}, "
                f"Unit: {node.get('unit','')}, "
                f"Intro: {node.get('intro','')}, "
                f"Value: {node.get('amount','')}"
            )

            # English LLM prompt
            prompt_msgs = SEMANTIC_BRIEF_PROMPT.format_messages(node_info=raw_info)
            prompt_text = "\n".join(getattr(m, "content", str(m)) for m in prompt_msgs)
            brief = (llm.generate_response(prompt_text) or "").strip()
            if brief:
                parts.append(brief[:150])
        except Exception as e:
            print(f"⚠️ LLM summary generation failed for Factor: {e}")

    # merge text fields
    for field in config["text_fields"]:
        if node_type == "Factor" and field == "intro":
            continue
        val = str(node.get(field, "") or "").strip()
        if val:
            parts.append(val)

    text = " ".join(parts).strip()
    return (config["prefix"] + text) if text else ""


# ---------------- Batch Processing ----------------
def process_batch(nodes: List[Dict[str, Any]], node_type: str,
                  embeddings: OllamaEmbeddings, vector_property: str,
                  llm: LLMWrapper = None) -> int:

    config = NODE_TYPES_CONFIG.get(node_type)
    if not config:
        return 0

    texts = []

    for row in nodes:
        node_props = dict(row["n"])
        text = get_node_text(node_props, config, llm=llm, node_type=node_type)
        if text:
            node_id = node_props.get("id")
            if node_id is None:
                continue
            texts.append((node_id, text))

    if not texts:
        return 0

    try:
        t0 = time.time()
        vectors = embeddings.embed_documents([t[1] for t in texts])
        print(f"  Generated {len(vectors)} vectors in {time.time()-t0:.2f}s")
    except Exception as e:
        print(f"❌ Embedding generation failed: {e}")
        return 0

    neo = Neo4jWrapper()
    try:
        for i, (node_id, _) in enumerate(tqdm(texts, desc="  Saving vectors", leave=False)):
            try:
                neo.execute_query(
                    f"MATCH (n:{node_type}) WHERE n.id = $nodeId "
                    f"SET n.{vector_property} = $vector",
                    {"nodeId": node_id, "vector": vectors[i]}
                )
            except Exception as e:
                print(f"  ❌ Failed to store vector for {node_id}: {e}")
    finally:
        neo.close()

    return len(texts)


# ---------------- Main Vectorization ----------------
def vectorize_nodes(embeddings: OllamaEmbeddings,
                    vector_property: str,
                    recompute_existing: bool = False,
                    selected_types: List[str] = None,
                    force_types: List[str] = None):

    selected_types = _normalize_types(selected_types or SELECTED_NODE_TYPES)
    force_set = set(_normalize_types(force_types or FORCE_RECOMPUTE_TYPES))
    target_types = _iter_target_types(selected_types)

    neo = Neo4jWrapper()
    llm = LLMWrapper()

    try:
        total = 0
        # Pre-count
        for node_type in target_types:
            config = NODE_TYPES_CONFIG[node_type]
            wc = config["where_clause"]

            if not (node_type in force_set or recompute_existing):
                wc += f" AND (n.{vector_property} IS NULL OR size(n.{vector_property}) = 0)"

            cnt_res = neo.execute_query(
                f"MATCH (n:{node_type}) {wc} RETURN count(*) AS cnt"
            )
            cnt = cnt_res[0]["cnt"] if cnt_res else 0
            total += cnt

            mode = "force recompute" if node_type in force_set else \
                   ("full recompute" if recompute_existing else "missing only")

            print(f"  - {config['label']} ({node_type}): {cnt} nodes ({mode})")

        if total == 0:
            print("✔ Nothing to vectorize.")
            return

        print(f"\nVectorizing {total} nodes ...")

        processed = 0
        for node_type in target_types:
            config = NODE_TYPES_CONFIG[node_type]
            wc = config["where_clause"]

            if not (node_type in force_set or recompute_existing):
                wc += f" AND (n.{vector_property} IS NULL OR size(n.{vector_property}) = 0)"

            print(f"\nProcessing {config['label']} ({node_type})...")
            nodes = neo.execute_query(f"MATCH (n:{node_type}) {wc} RETURN n")

            for i in range(0, len(nodes), BATCH_SIZE):
                batch = nodes[i:i + BATCH_SIZE]
                n = process_batch(batch, node_type, embeddings, vector_property, llm=llm)
                processed += n
                print(f"  Progress: {processed}/{total}")

        print(f"\n✔ Completed. {processed} nodes vectorized.")

    finally:
        neo.close()


# ---------------- Verification ----------------
def verify_vectorization(vector_property: str, selected_types: List[str] = None):
    selected_types = _normalize_types(selected_types or SELECTED_NODE_TYPES)
    target_types = _iter_target_types(selected_types)

    print("\nVerification:")
    neo = Neo4jWrapper()
    try:
        for node_type in target_types:
            config = NODE_TYPES_CONFIG[node_type]
            total = neo.execute_query(f"MATCH (n:{node_type}) RETURN count(*) AS total")[0]["total"]
            vect = neo.execute_query(
                f"MATCH (n:{node_type}) "
                f"WHERE n.{vector_property} IS NOT NULL AND size(n.{vector_property}) > 0 "
                f"RETURN count(*) AS v"
            )[0]["v"]

            pct = (vect / total * 100) if total else 0
            print(f"  - {node_type}: {vect}/{total} ({pct:.1f}%)")

    finally:
        neo.close()


# ---------------- Index Creation ----------------
def create_vector_index(vector_property: str, dimension: int = 4096,
                        selected_types: List[str] = None):

    selected_types = _normalize_types(selected_types or SELECTED_NODE_TYPES)
    target_types = _iter_target_types(selected_types)

    print(f"\nCreating vector indexes... (dim={dimension})")
    neo = Neo4jWrapper()

    try:
        for node_type in target_types:
            index_name = f"{node_type}_{vector_property}_idx"
            try:
                neo.execute_query(f"DROP INDEX {index_name} IF EXISTS")

                neo.execute_query(
                    f"""
                    CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                    FOR (n:{node_type}) ON (n.{vector_property})
                    OPTIONS {{
                        indexConfig: {{
                            `vector.dimensions`: {dimension},
                            `vector.similarity_function`: 'cosine'
                        }}
                    }}
                    """
                )
                print(f"  ✔ Created index for {node_type}")
            except Exception as e:
                print(f"  ⚠ Index creation failed for {node_type}: {e}")

    finally:
        neo.close()


# ---------------- Main ----------------
def carbon_vectorize(enhance_semantic=True):
    global ENABLE_SEMANTIC_ENHANCEMENT
    ENABLE_SEMANTIC_ENHANCEMENT = enhance_semantic
    print("=== Vectorizing Carbon Emission KG (Ontology Aligned) ===")
    print(f"Semantic enhancement: {'Enabled' if ENABLE_SEMANTIC_ENHANCEMENT else 'Disabled'}")

    try:
        embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.01
        )
        embeddings.embed_query("hello")
        print(f"✔ Ollama connected (model={EMBEDDING_MODEL})")
    except Exception as e:
        print(f"❌ Ollama connection failed: {e}")
        return

    vectorize_nodes(
        embeddings=embeddings,
        vector_property=VECTOR_PROPERTY,
        recompute_existing=RECOMPUTE_EXISTING,
        selected_types=SELECTED_NODE_TYPES,
        force_types=FORCE_RECOMPUTE_TYPES
    )

    verify_vectorization(VECTOR_PROPERTY, SELECTED_NODE_TYPES)
    create_vector_index(VECTOR_PROPERTY, dimension=4096, selected_types=SELECTED_NODE_TYPES)

    print("\n=== Done ===")
