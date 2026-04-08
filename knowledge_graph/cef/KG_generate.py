# -*- coding: utf-8 -*-
"""
Carbon Emission Factor Knowledge Graph Generator (Ontology Aligned)

Ontology Requirements:
----------------------
Generic classes have 3 categories:

  Time   (id, name, intro)
  Region (id, name, intro)
  Source (id, name, intro)

Emission factors must connect to all generic classes via:
    (factor)-[:BELONGS_TO]->(Time/Region/Source)

This script loads CSV data and constructs the aligned carbon-emission-factor KG.
"""

import csv
import os
import re
import sys
from typing import Dict, List, Any, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from configs.neo4j_wrapper import Neo4jWrapper


# ----------------------------------------------------------
# Neo4j client
# ----------------------------------------------------------
neo4j = Neo4jWrapper()


# ----------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------
def to_float_or_none(s: Any) -> Optional[float]:
    try:
        if s is None:
            return None
        if isinstance(s, str):
            s = s.strip()
            if s == "":
                return None
        return float(s)
    except Exception:
        return None


def clean_headers(reader: csv.DictReader) -> None:
    if reader.fieldnames:
        reader.fieldnames = [h.strip() for h in reader.fieldnames]


def clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for k, v in row.items():
        key = k.strip() if isinstance(k, str) else k
        if isinstance(v, str):
            vv = v.strip()
            cleaned[key] = vv if vv != "" else None
        else:
            cleaned[key] = v
    return cleaned


def safe_props(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


# ----------------------------------------------------------
# Load CSV data
# ----------------------------------------------------------
def load_database_data() -> List[Dict[str, Any]]:
    file_path = os.path.join(os.path.dirname(__file__), "data", "database.csv")
    rows = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        clean_headers(reader)
        for row in reader:
            rows.append(clean_row(row))
    return rows


def load_ref_data() -> Dict[str, str]:
    file_path = os.path.join(os.path.dirname(__file__), "data", "ref.csv")
    refs = {}
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        clean_headers(reader)
        for row in reader:
            r = clean_row(row)
            idx = r.get("Index") or ""
            name = r.get("Name") or ""
            if idx:
                refs[idx] = name
    return refs


# ----------------------------------------------------------
# Constraints
# ----------------------------------------------------------
def ensure_constraints() -> None:
    queries = [
        "CREATE CONSTRAINT factor_id IF NOT EXISTS FOR (f:Factor) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT region_id IF NOT EXISTS FOR (r:Region) REQUIRE r.id IS UNIQUE",
        "CREATE CONSTRAINT time_id   IF NOT EXISTS FOR (t:Time)   REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE",
    ]
    for q in queries:
        neo4j.execute_query(q, {})


# ----------------------------------------------------------
# KG Construction
# ----------------------------------------------------------
def create_factor_nodes(factors: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = dict(processed=0, upserts=0)

    for row in factors:
        stats["processed"] += 1

        code = (row.get("Code") or "").strip()
        if not code:
            continue

        props = safe_props({
            "name": row.get("Name"),
            "category": row.get("Type"),
            "unit": row.get("Unit"),
            "intro": row.get("Characteristics"),
            "amount": to_float_or_none(row.get("Amount"))
        })

        q = """
        MERGE (f:Factor {id:$id})
        SET f += $props
        """
        neo4j.execute_query(q, {"id": code, "props": props})
        stats["upserts"] += 1

    return stats


def create_region_and_time_links(factors: List[dict]) -> Dict[str, int]:
    stats = dict(region_links=0, time_links=0)

    for row in factors:
        code = (row.get("Code") or "").strip()
        if not code:
            continue

        # Region ------------------------------------------
        region_name = row.get("Location")
        region_id = (region_name or "unknown").lower().replace(" ", "_")

        q_region = """
        MERGE (r:Region {id:$rid})
        ON CREATE SET r.name = $rname, r.intro = ''
        WITH r
        MATCH (f:Factor {id:$fid})
        MERGE (f)-[:BELONGS_TO]->(r)
        """
        neo4j.execute_query(q_region, {"rid": region_id, "rname": region_name, "fid": code})
        stats["region_links"] += 1

        # Time --------------------------------------------
        year = row.get("Year")
        period_id = f"year_{year}" if year is not None else "year_unknown"
        period_name = str(year) if year else None

        q_time = """
        MERGE (t:Time {id:$tid})
        ON CREATE SET t.name = $tname, t.intro = ''
        WITH t
        MATCH (f:Factor {id:$fid})
        MERGE (f)-[:BELONGS_TO]->(t)
        """
        neo4j.execute_query(q_time, {"tid": period_id, "tname": period_name, "fid": code})
        stats["time_links"] += 1

    return stats


def create_source_links(factors: List[dict], ref_map: Dict[str, str]) -> Dict[str, int]:
    stats = dict(source_upserts=0, source_links=0)

    for row in factors:
        code = (row.get("Code") or "").strip()
        if not code:
            continue

        ref_raw = (row.get("Ref.") or row.get("Ref") or "").strip()
        if not ref_raw:
            continue

        ref_key = re.sub(r"[\[\]\s]", "", ref_raw)

        if ref_key.isdigit() and ref_key in ref_map:
            source_id = f"source_{ref_key}"
            source_name = ref_map[ref_key]
        else:
            source_id = f"source_{ref_key}"
            source_name = ref_key

        q = """
        MERGE (s:Source {id:$sid})
        ON CREATE SET s.name = $sname, s.intro = $sname
        WITH s
        MATCH (f:Factor {id:$fid})
        MERGE (f)-[:BELONGS_TO]->(s)
        """
        neo4j.execute_query(q, {"sid": source_id, "sname": source_name, "fid": code})
        stats["source_upserts"] += 1
        stats["source_links"] += 1

    return stats


# ----------------------------------------------------------
# Main pipeline
# ----------------------------------------------------------
def generate_knowledge_graph():
    print("Loading CSV data...")
    factors = load_database_data()
    ref_map = load_ref_data()

    print("Ensuring constraints...")
    ensure_constraints()

    print("Creating factor nodes...")
    fstats = create_factor_nodes(factors)
    print("Factor stats:", fstats)

    print("Linking Region & Time...")
    rt_stats = create_region_and_time_links(factors)
    print("Region/Time stats:", rt_stats)

    print("Linking Source...")
    sstats = create_source_links(factors, ref_map)
    print("Source stats:", sstats)

    print("Carbon Emission Factor KG generation completed!")
