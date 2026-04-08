# -*- coding: utf-8 -*-
"""
Compute semantic similarity between resource_item and Factor using existing embeddings,
delegating the similarity calculation to Neo4j (vector.similarity.cosine).

Ontology-aligned version (English labels + HAS_FACTOR relationship).

Changes from the original numpy-based version:
- Cosine similarity is computed inside Neo4j using vector.similarity.cosine.
- Python no longer reads or manipulates embedding vectors directly.
- Still supports:
  - High vs mid similarity thresholds (SIM_HIGH / SIMILARITY_THRESHOLD).
  - Optional LLM-based filtering for mid-range candidates.
  - Batch processing for all resource_item nodes.
  - Single-item debug interface for inspecting one resource_item in detail.

Ontology assumptions:
- Label `resource_item` → resource_item
- Label `factor`       → Factor
- Relationship         → HAS_FACTOR
- Relationship weight property → w  (w ∈ [0,1])
- Overall pattern: (resource_item)-[:HAS_FACTOR {w}]->(Factor)
"""

import os
import sys
import math
import json
from typing import Dict, List, Any, Tuple, Optional

from tqdm import tqdm

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper


# ==========================================================
# Config
# ==========================================================

BATCH_SIZE = 256                  # Number of resource_item nodes per batch (for progress logging)
SIMILARITY_THRESHOLD = 0.50       # Minimum cosine similarity to be considered at all
SIM_HIGH = 0.80                   # High-confidence similarity threshold
MAX_CONNECTIONS_PER_NODE = 20     # Max number of HAS_FACTOR edges per resource_item
K_LLM = 20                        # Max number of mid-confidence candidates passed to LLM

REL_TYPE = "HAS_FACTOR"           # Relationship type
WEIGHT_PROP = "w"                 # Relationship weight property

WRITE_CHUNK = 5000                # Chunk size for writing relationships


# ==========================================================
# Helpers
# ==========================================================

def truncate(s: str, max_len: int = 200) -> str:
    """Safely truncate a string to max_len characters."""
    s = s or ""
    return s if len(s) <= max_len else s[:max_len]


def filter_factors_with_llm(
    resource_item: Dict[str, Any],
    factors: List[Dict[str, Any]],
) -> List[str]:
    """
    Optional LLM filtering stage.

    Input:
        - resource_item: single resource_item metadata
        - factors: list of factor candidates with fields:
            {id, name, category, unit, intro}

    Output:
        - List of Factor IDs approved by the LLM.

    If anything goes wrong (LLM not available, bad JSON, etc.), this
    falls back to returning all candidate IDs.
    """
    from prompts import CEF_SIMILARITY_FILTER_PROMPT

    try:
        factor_list_text = []
        for f in factors:
            factor_list_text.append(
                f"ID: {f.get('id','')}\n"
                f"Name: {f.get('name','')}\n"
                f"Category: {f.get('category','')}\n"
                f"Unit: {f.get('unit','')}\n"
                f"Description: {truncate(f.get('intro',''))}\n"
            )
        factor_list_text = "\n".join(factor_list_text)

        prompt = CEF_SIMILARITY_FILTER_PROMPT.format(
            resource_name=resource_item.get("name", ""),
            resource_category=resource_item.get("category", ""),
            resource_unit=resource_item.get("unit", ""),
            resource_description=truncate(resource_item.get("intro", "")),
            factor_list=factor_list_text,
        )

        llm = LLMWrapper()
        response = llm.generate_response(prompt)
        ids = json.loads(response)
        return [str(x) for x in ids] if isinstance(ids, list) else []

    except Exception as e:
        print(f"[LLM] Fallback due to error: {e}")
        return [f.get("id") for f in factors if f.get("id")]


# ==========================================================
# Read from Neo4j
# ==========================================================

def get_resource_items_needing_edges() -> List[Dict[str, Any]]:
    """
    Return all resource_item nodes that have embeddings (embeddings stay in Neo4j).

    We only fetch metadata needed for:
        - LLM filtering (name/category/unit/intro)
        - Relationship construction (id)
    """
    neo = Neo4jWrapper()
    try:
        rows = neo.execute_query(
            """
            MATCH (n:resource_item)
            WHERE n.embedding IS NOT NULL
            RETURN n.id      AS id,
                   n.name    AS name,
                   n.category AS category,
                   n.unit    AS unit,
                   n.intro   AS intro
            """
        ) or []
        return rows
    finally:
        neo.close()


def count_factors_with_embeddings() -> int:
    """Return how many Factor nodes have non-null embeddings."""
    neo = Neo4jWrapper()
    try:
        rows = neo.execute_query(
            """
            MATCH (f:Factor)
            WHERE f.embedding IS NOT NULL
            RETURN count(f) AS c
            """
        ) or [{"c": 0}]
        return int(rows[0]["c"])
    finally:
        neo.close()


# ==========================================================
# Similarity computation in Neo4j
# ==========================================================

def compute_matches_for_resource_item(
    neo: Neo4jWrapper,
    resource: Dict[str, Any],
) -> List[Tuple[str, float]]:
    """
    Compute the best Factor matches for a single resource_item, using
    Neo4j's vector.similarity.cosine, and optionally filter mid-range
    candidates with an LLM.

    Returns:
        List of (factor_id, similarity) tuples, sorted by similarity
        in descending order, truncated to MAX_CONNECTIONS_PER_NODE.
    """

    rid = resource.get("id")
    if not rid:
        return []

    # Top-K candidates from Neo4j.
    # K is chosen to cover:
    #   - all high-confidence ones
    #   - up to K_LLM mid-confidence for LLM filtering
    K = max(MAX_CONNECTIONS_PER_NODE, K_LLM)
    rows = neo.execute_query(
        """
        MATCH (ri:resource_item {id:$rid})
        WHERE ri.embedding IS NOT NULL

        CALL db.index.vector.queryNodes(
            'Factor_embedding_idx',
            $topk,
            ri.embedding
        )
        YIELD node AS f, score AS sim

        WHERE sim >= $sim_thr

        RETURN
            f.id       AS factor_id,
            f.name     AS name,
            f.category AS category,
            f.unit     AS unit,
            f.intro    AS intro,
            sim        AS similarity
        ORDER BY similarity DESC
        LIMIT $topk
        """,
        {
            "rid": rid,
            "sim_thr": SIMILARITY_THRESHOLD,
            "topk": K,
        },
    ) or []


    if not rows:
        return []

    # Split into high-confidence and mid-confidence buckets
    high_rows = [r for r in rows if r["similarity"] >= SIM_HIGH]
    mid_rows = [
        r
        for r in rows
        if SIMILARITY_THRESHOLD <= r["similarity"] < SIM_HIGH
    ][:K_LLM]

    # LLM filtering for mid-confidence candidates
    relevant_ids = set()
    if mid_rows:
        mid_factors_for_llm = []
        for r in mid_rows:
            mid_factors_for_llm.append(
                {
                    "id": r.get("factor_id", ""),
                    "name": r.get("name", ""),
                    "category": r.get("category", ""),
                    "unit": r.get("unit", ""),
                    "intro": truncate(r.get("intro", "")),
                }
            )

        resource_stub = {
            "name": resource.get("name", ""),
            "category": resource.get("category", ""),
            "unit": resource.get("unit", ""),
            "intro": truncate(resource.get("intro", "")),
        }

        relevant_ids = set(filter_factors_with_llm(resource_stub, mid_factors_for_llm))

    # Collect final matches:
    #   - all high-confidence pairs
    #   - mid-range pairs approved by LLM
    passed: List[Tuple[str, float]] = []

    for r in high_rows:
        fid = r["factor_id"]
        sim = float(r["similarity"])
        passed.append((fid, sim))

    for r in mid_rows:
        fid = r["factor_id"]
        if fid in relevant_ids:
            sim = float(r["similarity"])
            passed.append((fid, sim))

    if not passed:
        return []

    # Sort and truncate
    passed.sort(key=lambda x: x[1], reverse=True)
    return passed[:MAX_CONNECTIONS_PER_NODE]


# ==========================================================
# Core: establish relationships
# ==========================================================

def establish_relationships():
    """
    Main pipeline to:
      1) Load all resource_item nodes that have embeddings.
      2) For each resource_item, let Neo4j compute cosine similarity
         to all Factor nodes (via vector.similarity.cosine).
      3) Optionally filter mid-confidence candidates with LLM.
      4) Delete old HAS_FACTOR relationships for all resource_item nodes.
      5) Write new HAS_FACTOR relationships with weight property w.
    """
    print("=== Establishing resource_item → Factor (HAS_FACTOR) relationships ===")

    resource_items = get_resource_items_needing_edges()
    if not resource_items:
        print("No resource_item nodes with embeddings found.")
        return

    factor_count = count_factors_with_embeddings()
    if factor_count == 0:
        print("No Factor nodes with embeddings found.")
        return

    print(f"resource_items: {len(resource_items)}")
    print(f"Factors (with embeddings): {factor_count}")

    neo = Neo4jWrapper()
    try:
        rows_to_write: List[Dict[str, Any]] = []
        all_r_ids = [r.get("id") for r in resource_items if r.get("id")]

        num_batches = math.ceil(len(resource_items) / BATCH_SIZE)
        total_rel = 0

        for bi in tqdm(range(num_batches), desc="Batch Progress", unit="batch"):
            batch = resource_items[bi * BATCH_SIZE : (bi + 1) * BATCH_SIZE]

            for r in batch:
                rid = r.get("id")
                if not rid:
                    continue

                matches = compute_matches_for_resource_item(neo, r)
                if not matches:
                    continue

                for fid, sim in matches:
                    rows_to_write.append(
                        {
                            "resource_id": rid,
                            "factor_id": fid,
                            "w": float(sim),
                        }
                    )

            tqdm.write(f"Batch {bi+1}/{num_batches}: collected {len(rows_to_write)} rows so far")

        # Remove duplicates from all_r_ids
        all_r_ids = [rid for rid in set(all_r_ids) if rid]

        # Delete old HAS_FACTOR relationships for these resource_item nodes
        try:
            neo.execute_query(
                f"""
                UNWIND $ids AS rid
                MATCH (r:resource_item {{id: rid}})-[rel:{REL_TYPE}]->(:Factor)
                DELETE rel
                """,
                {"ids": all_r_ids},
            )
        except Exception as e:
            print(f"⚠ Error deleting old relationships: {e}")

        # Write new relationships
        if not rows_to_write:
            print("No new relationships to write.")
            return

        query = f"""
        UNWIND $rows AS row
        MATCH (r:resource_item {{id: row.resource_id}})
        MATCH (f:Factor       {{id: row.factor_id}})
        MERGE (r)-[rel:{REL_TYPE}]->(f)
        SET rel.{WEIGHT_PROP} = row.w
        """

        for i in tqdm(
            range(0, len(rows_to_write), WRITE_CHUNK),
            desc="Writing relationships",
            unit="chunk",
        ):
            chunk = rows_to_write[i : i + WRITE_CHUNK]
            neo.execute_query(query, {"rows": chunk})
            total_rel += len(chunk)

        print(f"\n✔ Total relationships created (MERGE calls): {total_rel}")

    finally:
        neo.close()


def verify_relationships():
    """
    Simple verification helper:
      - count total HAS_FACTOR relationships
      - show a few top-weight examples
    """
    print("\nVerify HAS_FACTOR relationships...")
    neo = Neo4jWrapper()
    try:
        count = neo.execute_query(
            f"""
            MATCH (:resource_item)-[r:{REL_TYPE}]->(:Factor)
            RETURN count(r) AS c
            """
        )[0]["c"]

        print(f"Total relationships: {count}")

        samples = neo.execute_query(
            f"""
            MATCH (r:resource_item)-[rel:{REL_TYPE}]->(f:Factor)
            RETURN r.name AS resource,
                   f.name AS factor,
                   rel.{WEIGHT_PROP} AS w
            ORDER BY w DESC
            LIMIT 5
            """
        )

        for s in samples:
            print(f"  {s['resource']} -> {s['factor']} (w={s['w']:.3f})")

    finally:
        neo.close()


# ==========================================================
# Single-item debug interface
# ==========================================================

def debug_single_resource_item(
    resource_id: str,
    sim_threshold: float = 0.5,
    sim_high: float = 0.8,
    k_llm: int = 20,
    max_connections: int = 20,
    top_n_print: int = 50,
):
    """
    Debug interface:
    Compute and display semantic matches for ONE resource_item using
    Neo4j's vector.similarity.cosine, without writing any relationships.

    You can use this to inspect:
      - Raw similarity ranking from Neo4j
      - Which factors fall into high / mid buckets
      - Which mid-range factors are approved by the LLM
      - What the final matches would be if the pipeline were applied

    Parameters:
        resource_id     : ID of the resource_item node
        sim_threshold   : minimum similarity to consider
        sim_high        : high-confidence similarity threshold
        k_llm           : max mid-range candidates passed to LLM
        max_connections : max final matches to display (would-be edges)
        top_n_print     : how many top similarities to print from Neo4j
    """

    neo = Neo4jWrapper()
    try:
        # --- 1. Load the resource item metadata ---------------------------
        r_rows = neo.execute_query(
            """
            MATCH (n:resource_item {id:$rid})
            WHERE n.embedding IS NOT NULL
            RETURN n.id      AS id,
                   n.name    AS name,
                   n.category AS category,
                   n.unit    AS unit,
                   n.intro   AS intro
            """,
            {"rid": resource_id},
        )

        if not r_rows:
            print(f"[ERROR] No resource_item found with id={resource_id}")
            return

        r = r_rows[0]
        print("\n=== Resource Item ===")
        print(json.dumps(r, ensure_ascii=False, indent=2))

        # --- 2. Query Factor similarities directly in Neo4j --------------
        K = max(max_connections, k_llm, top_n_print)

        sim_rows = neo.execute_query(
            """
            MATCH (ri:resource_item {id:$rid})
            MATCH (f:Factor)
            WHERE ri.embedding IS NOT NULL
              AND f.embedding IS NOT NULL
            WITH ri, f,
                 vector.similarity.cosine(ri.embedding, f.embedding) AS sim
            WHERE sim >= $sim_thr
            RETURN f.id    AS factor_id,
                   f.name  AS name,
                   f.category AS category,
                   f.unit  AS unit,
                   f.intro AS intro,
                   sim     AS similarity
            ORDER BY similarity DESC
            LIMIT $topk
            """,
            {
                "rid": resource_id,
                "sim_thr": sim_threshold,
                "topk": K,
            },
        ) or []

        if not sim_rows:
            print("[INFO] No Factor nodes above similarity threshold.")
            return

        # --- 3. Print top similarities (raw Neo4j cosine) ----------------
        print("\n=== Top Similarities (Neo4j cosine) ===")
        for i, row in enumerate(sim_rows[:top_n_print]):
            print(
                f"{row['factor_id']:>10} | {row['name']:<40} "
                f"| sim={row['similarity']:.4f}"
            )

        # --- 4. Split into high / mid sets -------------------------------
        high_rows = [r for r in sim_rows if r["similarity"] >= sim_high]
        mid_rows = [
            r
            for r in sim_rows
            if sim_threshold <= r["similarity"] < sim_high
        ][:k_llm]

        print("\n=== High-confidence Matches (sim >= {:.2f}) ===".format(sim_high))
        if not high_rows:
            print("(none)")
        else:
            for row in high_rows:
                print(
                    f"[HIGH] {row['name']:<40}  sim={row['similarity']:.4f}"
                )

        print(
            "\n=== Mid-confidence Candidates ({:.2f} <= sim < {:.2f}) ===".format(
                sim_threshold, sim_high
            )
        )
        if not mid_rows:
            print("(none)")
        else:
            for row in mid_rows:
                print(
                    f"[MID]  {row['name']:<40}  sim={row['similarity']:.4f}"
                )

        # --- 5. LLM filtering for mid-confidence candidates --------------
        if mid_rows:
            mid_factors_for_llm = []
            for row in mid_rows:
                mid_factors_for_llm.append(
                    {
                        "id": row.get("factor_id", ""),
                        "name": row.get("name", ""),
                        "category": row.get("category", ""),
                        "unit": row.get("unit", ""),
                        "intro": truncate(row.get("intro", "")),
                    }
                )

            resource_stub = {
                "name": r.get("name", ""),
                "category": r.get("category", ""),
                "unit": r.get("unit", ""),
                "intro": truncate(r.get("intro", "")),
            }

            approved_ids = set(
                filter_factors_with_llm(resource_stub, mid_factors_for_llm)
            )
        else:
            approved_ids = set()

        print("\n=== LLM Approved IDs (mid-confidence) ===")
        print(approved_ids)

        # --- 6. Final "would-be" matches (no write) ----------------------
        final: List[Tuple[Dict[str, Any], float]] = []

        for row in high_rows:
            final.append((row, float(row["similarity"])))

        for row in mid_rows:
            if row["factor_id"] in approved_ids:
                final.append((row, float(row["similarity"])))

        final.sort(key=lambda x: x[1], reverse=True)
        final = final[:max_connections]

        print("\n=== FINAL MATCHES (NO WRITE) ===")
        if not final:
            print("(none)")
        else:
            for row, sim in final:
                print(
                    f"[FINAL] {row['name']:<40}  sim={sim:.4f} "
                    f"(factor_id={row['factor_id']})"
                )

        return final

    finally:
        neo.close()


# ==========================================================
# Main
# ==========================================================

def cef_work_builder():
    """
    Entry point used by external callers:
      - Build HAS_FACTOR relationships based on Neo4j-side similarity.
      - Then verify with a small summary.
    """
    establish_relationships()
    verify_relationships()
