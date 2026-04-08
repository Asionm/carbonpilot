# -*- coding: utf-8 -*-
"""
Engineering–Carbon Knowledge Graph Importer (STRICT Paper Ontology)

Ontology (Engineering Part) — exactly as paper defines:
    sub-division
        CONTAINS →
    specialty-subdivision
        CONTAINS →
    sub-item-work
        CONSUMES →
    resource-item

Content from JSON ("content") is stored into sub-item-work.intro.

Intermediate JSON layer (e.g. "人工土方") is REMOVED completely.
work_content layer is REMOVED completely.
items[] directly become sub-item-work.

Generic classes: Time, Region, Source
sub-item-work BELONGS_TO → Time/Region/Source.

Completely matches paper O = (C, A, R).
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
TARGET_DB = os.getenv("NEO4J_DATABASE")

DEBUG = False
LIMITS = (1, 1, 5)  # (sub-division, specialty-subdivision, items_per_category)
BATCH = 200


# =============================================================
# Normalization
# =============================================================
def to_halfwidth(s: str) -> str:
    out = []
    for ch in str(s):
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)

def normalize_id(raw: str) -> str:
    s = re.sub(r"[⁃−–—－]", "-", to_halfwidth(raw))
    s = re.sub(r"\s*-\s*", "-", s.strip())
    m = re.match(r"^(\d+)-(\d+)$", s)
    return f"{int(m.group(1))}-{int(m.group(2))}" if m else s

def normalize_unit(u: str) -> str:
    u = to_halfwidth(u).strip()
    u = re.sub(r"m\s*\^?\s*3", "m3", u)
    u = re.sub(r"m\s*\^?\s*2", "m2", u)
    return re.sub(r"\s+", "", u)


# =============================================================
# ID makers
# =============================================================
def _h(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:12]

def sdw_id(name): return f"SDW-{_h(name)}"
def ss_id(parent, name): return f"SS-{_h(parent + '|' + name)}"
def si_id(qid): return f"SI-{qid}"
def ri_id(cat, name): return f"RI-{cat}-{_h(name)}"


# =============================================================
# Cypher Templates (strict ontology)
# =============================================================
MERGE_SDW = """
MERGE (n:sub_division {id:$id})
SET n.name=$name, n.intro=$intro
"""

MERGE_SS = """
MATCH (p:sub_division {id:$parent_id})
MERGE (n:specialty_subdivision {id:$id})
SET n.name=$name, n.intro=$intro
MERGE (n)-[:CONTAINS]->(p)
"""

MERGE_SI = """
MATCH (p:specialty_subdivision {id:$parent_id})
MERGE (n:sub_item_work {id:$id})
SET n.name=$name, n.unit=$unit, n.intro=$intro
MERGE (n)-[:CONTAINS]->(p)
"""

MERGE_RESOURCE_AND_USE = """
UNWIND $rows AS row
MERGE (r:resource_item {id:row.resource_id})
SET r.name=row.name, r.category=row.category, r.unit=row.unit, r.intro=row.intro
WITH r, row
MATCH (si:sub_item_work {id:row.si_id})
MERGE (si)-[u:CONSUMES]->(r)
SET u.value=row.value
"""

MERGE_BELONGS_TO = """
MATCH (x {id:$x_id})
MATCH (y {id:$y_id})
MERGE (x)-[:BELONGS_TO]->(y)
"""


# =============================================================
# Generic nodes: Time / Region / Source
# =============================================================
def merge_generic(session, label: str, id: str, name: str, intro: str = ""):
    cypher = f"""
    MERGE (g:{label} {{id:$id}})
    SET g.name=$name, g.intro=$intro
    """
    session.run(cypher, id=id, name=name, intro=intro)


# =============================================================
# Import Logic (strict ontology)
# =============================================================
def import_graph(uri, user, pwd, target_db, data, debug=False, limits=(999,999,999)):
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # generic classes
    TIME_ID = "TIME-2020"
    REGION_ID = "REGION-CHINA"
    SOURCE_ID = "SOURCE-CHINA-QUOTA"

    with driver.session(database=target_db) as session:

        merge_generic(session, "Time", TIME_ID, "Around 2020")
        merge_generic(session, "Region", REGION_ID, "China")
        merge_generic(session, "Source", SOURCE_ID,
                      "Housing Construction & Decoration Engineering Quota")

        limit_sdw, limit_ss, limit_items = limits

        sdw_i = 0
        for sdw_name, ss_obj in data.items():
            sdw_i += 1
            if debug and sdw_i > limit_sdw:
                break

            sdw_name = to_halfwidth(sdw_name).strip()
            sdw = sdw_id(sdw_name)
            session.run(MERGE_SDW, id=sdw, name=sdw_name, intro="")

            ss_i = 0
            for ss_name, cat_obj in ss_obj.items():
                ss_i += 1
                if debug and ss_i > limit_ss:
                    break

                ss_name = to_halfwidth(ss_name).strip()
                ss = ss_id(sdw, ss_name)
                session.run(MERGE_SS, parent_id=sdw, id=ss, name=ss_name, intro="")

                item_i = 0

                # cat_obj keys are intermediate categories ("人工土方"): must be removed
                for _, work_list in cat_obj.items():

                    for work in work_list:
                        intro_text = to_halfwidth(work.get("content", "")).strip()
                        items = work.get("items", [])

                        for item in items:
                            item_i += 1
                            if debug and item_i > limit_items:
                                break

                            qid = normalize_id(item.get("id", ""))
                            if not qid:
                                continue

                            si = si_id(qid)
                            si_name = to_halfwidth(item.get("name", "")).strip()
                            si_unit = normalize_unit(item.get("unit", ""))

                            session.run(MERGE_SI,
                                parent_id=ss,
                                id=si,
                                name=si_name,
                                unit=si_unit,
                                intro=intro_text  # <-- content goes to sub_item_work.intro
                            )

                            session.run(MERGE_BELONGS_TO, x_id=si, y_id=TIME_ID)
                            session.run(MERGE_BELONGS_TO, x_id=si, y_id=REGION_ID)
                            session.run(MERGE_BELONGS_TO, x_id=si, y_id=SOURCE_ID)

                            acts = item.get("activities", {})
                            batch = []

                            for cat_key, cat_label in (
                                ("labor", "Labor"),
                                ("material", "Material"),
                                ("machinery", "Machinery")
                            ):
                                for r in acts.get(cat_key, []) or []:
                                    name = to_halfwidth(r.get("name", "")).strip()
                                    if not name:
                                        continue
                                    try:
                                        val = float(r.get("value"))
                                    except:
                                        continue

                                    unit = normalize_unit(r.get("unit", "")) or ""
                                    rid = ri_id(cat_label, name)

                                    batch.append({
                                        "resource_id": rid,
                                        "name": name,
                                        "category": cat_label,
                                        "unit": unit,
                                        "intro": "",
                                        "si_id": si,
                                        "value": val
                                    })

                            if batch:
                                session.run(MERGE_RESOURCE_AND_USE, rows=batch)

    driver.close()


# =============================================================
# Public API
# =============================================================
def generate_quota_knowledge(input_file="knowledge_graph/quota/static/structured_llm_augmented.json"):
    data = json.loads(Path(input_file).read_text("utf-8"))
    limits = LIMITS if DEBUG else (999999999,) * 3

    import_graph(
        uri=NEO4J_URI,
        user=NEO4J_USERNAME,
        pwd=NEO4J_PASSWORD,
        target_db=TARGET_DB,
        data=data,
        debug=DEBUG,
        limits=limits
    )
