# -*- coding: utf-8 -*-
"""
Information enhancement for WBS (LLM + KG optional).

This module works on a WBS JSON tree with the following level hierarchy:

  construction_project
    → individual_project
      → unit_project
        → sub_divisional_work
          → specialty_subdivision
            → sub_item_work

Stage1 (optional): LLM-based name + description enhancement for sub_item_work.
Stage2 (optional): KG + LLM-based classification into sub_divisional_work
                   and specialty_subdivision, and reorganization under
                   each unit_project.
"""

import json
import logging
from typing import Dict, List, Tuple, Any, Optional

log = logging.getLogger(__name__)

# ========== Optional dependencies (only used when LLM / KG are enabled) ==========
try:
    from configs.llm_wrapper import LLMWrapper
    from prompts import ENHANCEMENT_BATCH_PROCESS_PROMPT, ENHANCEMENT_CLASSIFICATION_PROMPT
    from configs.neo4j_wrapper import Neo4jWrapper
    from knowledge_graph.quota.query.query import local_semantic_search
except Exception:  # allow running in minimal/offline environments
    LLMWrapper = None
    Neo4jWrapper = None
    ENHANCEMENT_BATCH_PROCESS_PROMPT = ENHANCEMENT_CLASSIFICATION_PROMPT = ""
    local_semantic_search = None


# ========== Basic I/O utilities ==========
def load_wbs(path: str) -> Dict[str, Any]:
    """Load a WBS JSON file from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_wbs(path: str, data: Dict[str, Any]) -> None:
    """Save a WBS JSON object to disk."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_key(path_info: List[Dict[str, str]], raw_name: str) -> str:
    """
    Build a stable key for a leaf sub_item_work node based on its path and original name.
    This is used to look up enhancement/classification results.
    """
    p = " / ".join(f"{x.get('level','')}:{x.get('name','')}" for x in path_info)
    return f"{p} // sub_item:{raw_name}"


def iter_sub_items(node: Dict[str, Any], path=None) -> List[Tuple[Dict[str, Any], List[Dict[str, str]]]]:
    """
    Recursively traverse the WBS tree and collect all sub_item_work nodes
    along with their path (list of {level, name}).
    """
    path = (path or []) + [{"level": node.get("level", ""), "name": node.get("name", "")}]
    if node.get("level") == "sub_item_work":
        return [(node, path)]

    out: List[Tuple[Dict[str, Any], List[Dict[str, str]]]] = []
    for ch in node.get("children", []):
        out += iter_sub_items(ch, path)
    return out


# ========== Stage 1: LLM batch enhancement (name + short description) ==========
def enhance_batch(llm, items: List[Dict[str, Any]], context: str) -> List[Dict[str, str]]:
    """
    Enhance a batch of sub_item_work nodes (name + description) using LLM.

    If llm is None, this function simply truncates original descriptions
    to a short form and returns them as-is.
    """
    # Fallback: no LLM, return simple truncated descriptions
    if not llm or not items:
        return [
            {
                "name": it["name"],
                "description": (it.get("description", "") or "")[:50],
            }
            for it in items
        ]

    # Construct LLM prompt
    prompt = ENHANCEMENT_BATCH_PROCESS_PROMPT.format(
        context=context,
        items_info="\n".join(
            f"- name:{it['name']}, description:{it.get('description','')}" for it in items[:20]
        ),
    )

    try:
        data = json.loads(llm.generate_response(prompt) or "[]")
    except Exception as e:
        log.warning("LLM batch enhancement failed: %s, falling back to original texts", e)
        data = []

    out: List[Dict[str, str]] = []
    for i, it in enumerate(items):
        if i < len(data):
            out.append(
                {
                    "name": data[i].get("name", it["name"]),
                    "description": data[i].get("description", (it.get("description", "") or "")[:50]),
                }
            )
        else:
            out.append(
                {
                    "name": it["name"],
                    "description": (it.get("description", "") or "")[:50],
                }
            )
    return out


# ========== Stage 2: KG search + LLM selection (optional) ==========
def kg_search(driver, node_type: str, q: str, k: int = 10, parent_id: Optional[str] = None) -> List[Dict]:
    """
    Query the local KG using semantic search.

    node_type: e.g., 'sub_divisional_work', 'specialty_subdivision', etc.
    q:        query text
    k:        top-k results
    parent_id: optional parent node id for filtering specialty_subdivision
    """
    if not local_semantic_search:
        return []

    try:
        return local_semantic_search(
            driver=driver, node_type=node_type, query_text=q, top_k=k, parent_node_id=parent_id
        )
    except TypeError:
        # Backward compatibility for older function signature without parent_node_id
        res = local_semantic_search(driver=driver, node_type=node_type, query_text=q, top_k=k)
        if not parent_id:
            return res

        keys, out = ("parent_id", "parentId", "division_id"), []
        for r in res:
            props = r.get("properties", {})
            pid = next((props.get(key) for key in keys if props.get(key)), None)
            if pid == parent_id:
                out.append(r)
        return out or res


def llm_pick_best(llm, work_name: str, context: str, cands: List[Dict]) -> str:
    """
    Ask LLM to pick the best candidate from KG search results.
    Returns the chosen candidate id (string), or "" if no decision.
    """
    if not llm or not cands:
        return ""

    info = [
        {
            "id": c.get("properties", {}).get("id", ""),
            "name": c.get("properties", {}).get("name", ""),
            "intro": c.get("properties", {}).get("intro", ""),
        }
        for c in cands
    ]

    prompt = ENHANCEMENT_CLASSIFICATION_PROMPT.format(
        work_name=work_name,
        context=context,
        candidates=json.dumps(info, ensure_ascii=False),
    )

    try:
        return (llm.generate_response(prompt) or "").strip().strip('"')
    except Exception as e:
        log.warning("LLM classification selection failed: %s", e)
        return ""


def classify_one(driver, llm, sub_item: Dict[str, Any], path_info: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Classify a single sub_item_work node into:
      - best_division_name         (sub_divisional_work name)
      - best_specialty_subdivision_name
    using KG + LLM.

    Returns a dict with the best division/specialty names and path_info.
    """
    name = sub_item.get("name", "")
    desc = sub_item.get("description", "") or ""
    context = " -> ".join(f"{x['level']}:{x['name']}" for x in path_info)
    q = f"{name} {desc}".strip()

    # First: search candidate sub_divisional_work
    div_cands = kg_search(driver, "sub_division", q, 10)
    best_div_id = llm_pick_best(llm, name, context, div_cands)
    best_div_name = next(
        (c.get("properties", {}).get("name", "") for c in div_cands if c.get("properties", {}).get("id") == best_div_id),
        "",
    )

    sub_cands: List[Dict] = []
    best_sub_name = ""
    if best_div_id:
        # Then: search candidate specialty_subdivision under chosen division
        sub_cands = kg_search(driver, "specialty_subdivision", q, 10, parent_id=best_div_id)
        best_sub_id = llm_pick_best(llm, name, context, sub_cands)
        best_sub_name = next(
            (c.get("properties", {}).get("name", "") for c in sub_cands if c.get("properties", {}).get("id") == best_sub_id),
            "",
        )

    return {
        "best_division_name": best_div_name,
        "best_specialty_subdivision_name": best_sub_name,
        "path_info": path_info,
        "description": sub_item.get("description", ""),
    }


# ========== Stage 2: reorganize under each unit_project ==========
def reorganize(collected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reorganize all classified sub_item_work under a unit_project.

    Input: collected is a list of items:
      {
        "node": <sub_item_work dict>,
        "classification": {
           "best_division_name": str,
           "best_specialty_subdivision_name": str,
           "path_info": [...],
        }
      }

    Output: a list of sub_divisional_work nodes, each containing specialty_subdivision
    nodes, which in turn contain sub_item_work children.
    """
    groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for it in collected:
        node = it["node"]
        c = it.get("classification") or {}

        div = (c.get("best_division_name") or "").strip()
        sub = (c.get("best_specialty_subdivision_name") or "").strip()

        if not div:
            div = "Unclassified Divisional Work"

        if not sub:
            sub = "Unclassified Specialty Subdivision"

        groups.setdefault(div, {}).setdefault(sub, []).append(node)

    out: List[Dict[str, Any]] = []

    for div, subs in groups.items():
        div_node = {
            "level": "sub_divisional_work",
            "name": div,
            "description": "",
            "children": [],
        }

        for sub, items in subs.items():
            sub_node = {
                "level": "specialty_subdivision",
                "name": sub,
                "description": "",
                "children": [],
            }

            for x in items:
                item = x.copy()
                item["level"] = "sub_item_work"
                # ensure required fields exist; unit/quantity are assumed pre-existing
                sub_node["children"].append(item)

            div_node["children"].append(sub_node)

        out.append(div_node)

    return out


def build_enhanced_tree(
    node: Dict[str, Any],
    cr_map: Dict[str, Dict[str, Any]],
    path=None,
    reorganize_unclassified: bool = True,
    write_classification: bool = True,
) -> Dict[str, Any]:
    """
    Rebuild an enhanced WBS tree by applying Stage1 + Stage2 results.

    Parameters:
    - reorganize_unclassified:
        True  -> Under each unit_project, regroup all sub_item_work into
                 sub_divisional_work / specialty_subdivision / sub_item_work.
        False -> Keep original hierarchy; only write back enhanced name/description.
    - write_classification:
        True  -> Write classification field into leaf nodes (Stage2 ON).
        False -> Do not write classification field.
    """
    path = (path or []) + [{"level": node.get("level", ""), "name": node.get("name", "")}]

    # Leaf: sub_item_work
    if node.get("level") == "sub_item_work":
        enriched = node.copy()
        stable_key = make_key(path, (enriched.get("raw_name") or enriched.get("name", "")))
        cr = cr_map.get(stable_key)

        # Only write back name / description; classification is optional
        if cr and cr.get("name"):
            enriched["name"] = cr["name"]
        if cr and cr.get("description"):
            enriched["description"] = cr["description"]

        if write_classification:
            enriched["classification"] = {
                "best_division_name": (cr or {}).get("best_division_name", ""),
                "best_specialty_subdivision_name": (cr or {}).get("best_specialty_subdivision_name", ""),
                "path_info": path,
            }

        return enriched

    # Non-leaf node
    if node.get("children"):
        enriched = node.copy()

        # Special handling at unit_project level
        if node.get("level") == "unit_project":
            bag: List[Dict[str, Any]] = []

            def collect(n: Dict[str, Any], p: List[Dict[str, str]]) -> None:
                p2 = p + [{"level": n.get("level", ""), "name": n.get("name", "")}]
                if n.get("level") == "sub_item_work":
                    sk = make_key(p2, (n.get("raw_name") or n.get("name", "")))
                    base = {
                        "node": n.copy(),
                        "classification": {
                            "best_division_name": "",
                            "best_specialty_subdivision_name": "",
                            "path_info": p2,
                        },
                    }
                    c = cr_map.get(sk)
                    if c:
                        if c.get("name"):
                            base["node"]["name"] = c["name"]
                        if c.get("description"):
                            base["node"]["description"] = c["description"]
                        base["classification"]["best_division_name"] = c.get("best_division_name", "")
                        base["classification"]["best_specialty_subdivision_name"] = c.get(
                            "best_specialty_subdivision_name", ""
                        )
                    bag.append(base)
                else:
                    for ch in n.get("children", []):
                        collect(ch, p2)

            # Collect all sub_item_work descendants under this unit_project
            for ch in node.get("children", []):
                collect(ch, path)

            if reorganize_unclassified:
                # Stage2 ON: reorganize unit_project children into divisional / specialty structure.
                enriched["children"] = reorganize(bag)
                # Note: sub_item_work nodes inside reorganize do not carry classification field by design.
                # If you want to keep it, you can extend reorganize() to propagate classification.
            else:
                # Stage2 OFF: keep original hierarchy, only write back name/description (no classification)
                enriched["children"] = [
                    build_enhanced_tree(
                        ch,
                        cr_map,
                        path,
                        reorganize_unclassified=False,
                        write_classification=False,
                    )
                    for ch in node.get("children", [])
                ]
        else:
            # All other non-leaf levels: recurse normally
            enriched["children"] = [
                build_enhanced_tree(
                    ch,
                    cr_map,
                    path,
                    reorganize_unclassified=reorganize_unclassified,
                    write_classification=write_classification,
                )
                for ch in node.get("children", [])
            ]

        return enriched

    # Node without children
    return node


# ========== Main entrypoint (Stage1 / Stage2 controlled independently) ==========
def enhance_information(
    input_file: str,
    output_file: str,
    use_llm_stage1: bool = False,
    use_llm_stage2: bool = False,
    batch_size: int = 8,
) -> Dict[str, Any]:
    """
    Enhance a WBS JSON file in two optional stages.

    Parameters:
    - use_llm_stage1:
        False -> Do not use LLM for name/description enhancement (keep original).
        True  -> Use LLM to normalize name + generate short description for sub_item_work.
    - use_llm_stage2:
        False -> Do not classify into sub_divisional_work / specialty_subdivision,
                 keep original hierarchy, do not write classification field.
        True  -> Use KG + LLM to classify and rebuild unit_project subtree
                 into sub_divisional_work / specialty_subdivision / sub_item_work.
    - batch_size:
        Number of sub_item_work to send per LLM batch in Stage1.

    When both Stage1 and Stage2 are False, the original structure is passed through unchanged.
    """
    log.info(
        "Start WBS enhancement: %s -> %s (Stage1=%s, Stage2=%s)",
        input_file,
        output_file,
        use_llm_stage1,
        use_llm_stage2,
    )

    wbs = load_wbs(input_file)

    if not use_llm_stage1 and not use_llm_stage2:
        # Both stages disabled: direct passthrough
        save_wbs(output_file, wbs)
        log.info("All stages disabled: original WBS has been written as-is.")
        return wbs

    # Initialize LLM and Neo4j driver if needed
    llm = None
    driver = None
    try:
        if use_llm_stage1 or use_llm_stage2:
            llm = LLMWrapper() if LLMWrapper else None
        driver = Neo4jWrapper().get_driver() if Neo4jWrapper else None
    except Exception as e:
        log.warning("Initialization failed: %s, falling back to passthrough WBS.", e)
        save_wbs(output_file, wbs)
        return wbs

    # Collect all sub_item_work nodes
    pairs = iter_sub_items(wbs)
    log.info("Found %d sub_item_work nodes", len(pairs))

    # ---------- Stage1: name + description enhancement ----------
    enhanced_pairs: List[Tuple[Dict[str, Any], List[Dict[str, str]]]] = []
    for i in range(0, len(pairs), batch_size):
        batch = pairs[i : i + batch_size]
        items = [{"name": s.get("name", ""), "description": s.get("description", "")} for s, _ in batch]
        context = " -> ".join(f"{p['level']}:{p['name']}" for p in (batch[0][1] if batch else []))
        enh = enhance_batch(llm if use_llm_stage1 else None, items, context)

        for (sub, path), e in zip(batch, enh):
            sub2 = sub.copy()
            sub2["raw_name"] = sub.get("raw_name") or sub.get("name", "")
            sub2["name"], sub2["description"] = e["name"], e["description"]
            sub2["_stable_key"] = make_key(path, sub2["raw_name"])
            enhanced_pairs.append((sub2, path))

    # ---------- Stage2: KG + LLM classification (optional) ----------
    cr_map: Dict[str, Dict[str, Any]] = {}

    for sub2, path in enhanced_pairs:
        sk = sub2.get("_stable_key") or make_key(path, sub2.get("raw_name") or sub2.get("name", ""))
        if not use_llm_stage2:
            # No classification: only propagate enhanced name/description
            cr_map[sk] = {
                "best_division_name": "",
                "best_specialty_subdivision_name": "",
                "path_info": path,
                "description": sub2.get("description", ""),
                "name": sub2.get("name", ""),
            }
            continue

        cr = classify_one(driver, llm, sub2, path)
        cr_map[sk] = {
            "best_division_name": cr.get("best_division_name", ""),
            "best_specialty_subdivision_name": cr.get("best_specialty_subdivision_name", ""),
            "path_info": cr.get("path_info", []),
            "description": sub2.get("description", ""),
            "name": sub2.get("name", ""),
        }

    # Stage2 flags control reorganization and classification output
    enhanced = build_enhanced_tree(
        wbs,
        cr_map,
        reorganize_unclassified=use_llm_stage2,
        write_classification=use_llm_stage2,
    )

    save_wbs(output_file, enhanced)
    log.info("WBS enhancement finished: %s", output_file)
    return enhanced
