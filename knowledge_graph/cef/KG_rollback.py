# -*- coding: utf-8 -*-
"""
Carbon Emission Factor Knowledge Graph Rollback Script
(clean, schema-aware version)

This script performs a full rollback of the Carbon Emission Factor (CEF)
subgraph inside Neo4j, including:

1. Delete all :factor nodes and their relationships.
2. Delete orphan :region / :period / :CEF_source nodes.
3. Optionally remove constraints and indexes related to these labels
   so that they no longer appear in the Neo4j Schema Panel.
4. Optional selective rollback by keyword/pattern.

Intended usage:
- Full rollback:
      python cef/CEF_work_rollback.py
- With schema cleanup:
      python cef/CEF_work_rollback.py --drop-schema
- Force delete all related nodes (DANGEROUS):
      python cef/CEF_work_rollback.py --force-all
- Selective rollback (remove factors matching name/id/category):
      selective_rollback("cement")
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from configs.neo4j_wrapper import Neo4jWrapper

# These constraint names must match those created during CEF graph construction
CONSTRAINT_NAMES = ["factor_id", "region_id", "period_id", "source_id"]

# Labels affected by rollback
AFFECTED_LABELS = ["factor", "region", "period", "CEF_source"]


# ===================================================================
# Schema cleanup: constraints & indexes
# ===================================================================
def _drop_schema(neo4j: Neo4jWrapper):
    """
    Drop constraints and indexes associated with factor/region/period/source labels.

    Performs:
    - Explicit DROP CONSTRAINT for known constraint names.
    - Fallback: remove all automatically generated constraints/indexes that
      target these labels (schema cleanup for Neo4j Browser).
    """
    # 1) Drop constraints created explicitly during ingestion
    for name in CONSTRAINT_NAMES:
        neo4j.execute_query(f"DROP CONSTRAINT {name} IF EXISTS", {})

    # 2) Discover and drop any remaining indexes/constraints using SHOW INDEXES
    q_indexes = """
    SHOW INDEXES YIELD name, entityType, labelsOrTypes
    WHERE any(l IN labelsOrTypes WHERE l IN $labels)
    RETURN name
    """
    res = neo4j.execute_query(q_indexes, {"labels": AFFECTED_LABELS}) or []

    to_drop = []
    for row in res:
        try:
            to_drop.append(row.get("name"))
        except Exception:
            pass

    for idx in filter(None, to_drop):
        neo4j.execute_query(f"DROP CONSTRAINT {idx} IF EXISTS", {})


# ===================================================================
# Graph deletion (factor + orphan cleanup)
# ===================================================================
def _delete_graph(neo4j: Neo4jWrapper):
    """
    Delete the factor subgraph:
    - Remove all :factor nodes and their relationships.
    - Remove any orphan region/period/source nodes.
    """
    # 1) Delete all factors (DETACH DELETE removes all relationships)
    neo4j.execute_query("""MATCH (f:factor) DETACH DELETE f""", {})

    # 2) Remove orphan nodes
    neo4j.execute_query("""MATCH (n:region)     WHERE NOT (n)--() DETACH DELETE n""", {})
    neo4j.execute_query("""MATCH (n:period)     WHERE NOT (n)--() DETACH DELETE n""", {})
    neo4j.execute_query("""MATCH (n:CEF_source) WHERE NOT (n)--() DETACH DELETE n""", {})

    # Optional but dangerous: force delete all related nodes regardless of connectivity
    # Uncomment only for full cleanup of these labels:
    # neo4j.execute_query("""MATCH (n:region)     DETACH DELETE n""", {})
    # neo4j.execute_query("""MATCH (n:period)     DETACH DELETE n""", {})
    # neo4j.execute_query("""MATCH (n:CEF_source) DETACH DELETE n""", {})


# ===================================================================
# Verification of final graph state
# ===================================================================
def _verify(neo4j: Neo4jWrapper):
    """
    Print counts of remaining nodes and relationships for verification.
    """

    checks = [
        ("factor",      "MATCH (n:factor) RETURN count(n) AS cnt"),
        ("region",      "MATCH (n:region) RETURN count(n) AS cnt"),
        ("period",      "MATCH (n:period) RETURN count(n) AS cnt"),
        ("CEF_source",  "MATCH (n:CEF_source) RETURN count(n) AS cnt"),
        ("rels",        "MATCH ()-[r]-() RETURN count(r) AS cnt"),
    ]

    for name, q in checks:
        try:
            res = neo4j.execute_query(q, {}) or []
            print(f"[VERIFY] {name}: {res}")
        except Exception as e:
            print(f"[VERIFY] {name} query failed: {e}")

    # For manual verification (recommended):
    # CALL db.labels();
    # SHOW CONSTRAINTS;
    # SHOW INDEXES;


# ===================================================================
# Full rollback API
# ===================================================================
def rollback_cef_knowledge_graph(drop_schema: bool = False, force_wipe_all_related: bool = False):
    """
    Perform a full rollback of the Carbon Emission Factor subgraph.

    Args:
        drop_schema (bool):
            Whether to drop all constraints and indexes associated with
            factor/region/period/CEF_source labels.

        force_wipe_all_related (bool):
            If True: forcibly remove ALL region, period, CEF_source nodes
            even if they are not orphans. (DANGEROUS)

    Recommended usage:
        rollback_cef_knowledge_graph(drop_schema=True)
    """
    neo4j = Neo4jWrapper()
    try:
        print("Deleting factor graph ...")
        _delete_graph(neo4j)

        if force_wipe_all_related:
            print("Force wiping ALL region/period/CEF_source nodes (DANGEROUS) ...")
            neo4j.execute_query("""MATCH (n:region)     DETACH DELETE n""", {})
            neo4j.execute_query("""MATCH (n:period)     DETACH DELETE n""", {})
            neo4j.execute_query("""MATCH (n:CEF_source) DETACH DELETE n""", {})

        if drop_schema:
            print("Dropping constraints and indexes ...")
            _drop_schema(neo4j)

        print("Verifying final state ...")
        _verify(neo4j)

        print("Rollback completed.")

    except Exception as e:
        print(f"Error during rollback: {e}")
    finally:
        neo4j.close()


# ===================================================================
# Selective rollback API
# ===================================================================
def selective_rollback(pattern: str = None):
    """
    Selectively remove factor nodes whose id/name/category contains the given pattern.

    Args:
        pattern (str): Substring used to match target factor nodes.
    """
    neo4j = Neo4jWrapper()

    try:
        if not pattern:
            print("No pattern provided for selective rollback.")
            return

        print(f"Deleting factors matching pattern: {pattern!r}")

        # Remove matching factor nodes
        neo4j.execute_query(
            """
            MATCH (f:factor)
            WHERE coalesce(f.id,'') CONTAINS $p
               OR coalesce(f.name,'') CONTAINS $p
               OR coalesce(f.category,'') CONTAINS $p
            DETACH DELETE f
            """,
            {"p": pattern},
        )

        # Remove newly orphaned supporting nodes
        neo4j.execute_query("""MATCH (n:region)     WHERE NOT (n)--() DETACH DELETE n""", {})
        neo4j.execute_query("""MATCH (n:period)     WHERE NOT (n)--() DETACH DELETE n""", {})
        neo4j.execute_query("""MATCH (n:CEF_source) WHERE NOT (n)--() DETACH DELETE n""", {})

        print("Selective rollback completed.")

    except Exception as e:
        print(f"Error during selective rollback: {e}")
    finally:
        neo4j.close()


# ===================================================================
# CLI
# ===================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rollback Carbon Emission Factor (CEF) Knowledge Graph")

    parser.add_argument("--drop-schema", action="store_true", help="Drop constraints and indexes associated with the subgraph")
    parser.add_argument("--force-all",   action="store_true", help="Force-delete ALL region/period/source nodes (dangerous)")

    args = parser.parse_args()

    rollback_cef_knowledge_graph(
        drop_schema=args.drop_schema,
        force_wipe_all_related=args.force_all
    )
