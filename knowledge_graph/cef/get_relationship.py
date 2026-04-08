from typing import Any, Dict, List, Literal, Optional
import re
import numpy as np

from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper
from prompts import CEF_RERANK_PROMPT, RISK_PROMPT
from knowledge_graph.quota.query import query as vector_query
from knowledge_graph.cef.cef_cache import (
    load_cef_cache, save_cef_cache,
    get_cached_cef_result, save_cef_result_to_cache
)

# ===========================
# Six parallel modes
# ===========================
Mode = Literal[
    "similarity",   # Graph database similarity
    "rerank",       # LLM re-ranking
    "cost",         # Risk decision (including carbon price and penalty)
    "prob",         # Factor with highest probability
    "avg",          # Probability × factor value weighted average
    "max_ef"        # Factor with maximum factor value
]

CEF_CACHE_FILE = "static/cef_cache/rerank_cache.json"


# ======================
# Utility functions
# ======================

def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _minmax_norm(values: List[float]) -> List[float]:
    if not values:
        return []
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return [1.0] * len(values)
    return [(v - vmin) / (vmax - vmin) for v in values]


def get_recent_year(period: Any) -> int:
    if not period:
        return -1
    m = re.search(r'(19|20)\d{2}', str(period))
    return int(m.group(0)) if m else -1


# ======================
# Query candidate factors
# ======================

def _query_factors_by_rid(rid: str, limit: int = 50) -> List[Dict[str, Any]]:
    cypher = """
    MATCH (r:resource_item {id: $rid})-[rel:HAS_FACTOR]->(f:Factor)
    OPTIONAL MATCH (f)-[:BELONGS_TO]->(p:Time)
    OPTIONAL MATCH (f)-[:BELONGS_TO]->(rg:Region)
    OPTIONAL MATCH (f)-[:BELONGS_TO]->(s:Source)
    RETURN
        f.id     AS id,
        f.name   AS name,
        f.amount AS amount,
        f.unit   AS unit,
        f.intro  AS intro,
        rel.w    AS similarity,
        p.name   AS period,
        rg.name  AS region,
        s.name   AS source
    ORDER BY similarity DESC
    LIMIT $limit
    """
    neo = Neo4jWrapper()
    try:
        rows = neo.execute_query(cypher, {"rid": rid, "limit": limit}) or []
    finally:
        neo.close()
    return rows


def _semantic_find_resource(query_text: str, top_k: int = 5) -> Optional[str]:
    sem = vector_query.local_semantic_search(
        Neo4jWrapper().get_driver(), "resource_item", query_text, top_k=top_k
    ) or []

    for c in sem:
        props = c.get("properties") or {}
        cid = props.get("id") or c.get("id")
        if cid:
            return cid
    return None


def _get_resource_name_by_id(rid: str) -> Optional[str]:
    cypher = "MATCH (r:resource_item {id: $rid}) RETURN r.name AS name LIMIT 1"
    neo = Neo4jWrapper()
    try:
        rows = neo.execute_query(cypher, {"rid": rid}) or []
    finally:
        neo.close()
    return rows[0].get("name") if rows else None


def get_candidate_factors(resource_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    rid = resource_item.get("id") or resource_item.get("resource_id")
    rname = resource_item.get("name") or resource_item.get("resource_name")

    if rid:
        rows = _query_factors_by_rid(rid)
        if rows:
            return rows

    query_text = rname or rid
    if query_text:
        sem_id = _semantic_find_resource(query_text)
        if sem_id:
            return _query_factors_by_rid(sem_id)

    return []


# ======================
# Mode: rerank
# ======================

def llm_pick_best(
    project_info: str,
    resource_item: Dict[str, Any],
    cef_list: List[Dict[str, Any]]
) -> Optional[str]:

    factor_ids = sorted([str(f["id"]) for f in cef_list])
    cache_key = f"{resource_item.get('name')}_{'_'.join(factor_ids)}"

    cache = load_cef_cache(CEF_CACHE_FILE)
    cached = get_cached_cef_result(cache, cache_key)
    if cached:
        return cached

    factor_list_str = "\n".join([
        f"{i+1}. id:{f['id']} name:{f['name']} unit:{f['unit']} intro:{f['intro']} "
        f"amount:{f['amount']} time:{f['period']} region:{f['region']} "
        for i, f in enumerate(cef_list)
    ])

    prompt = CEF_RERANK_PROMPT.format(
        project_info=project_info,
        resource_name=resource_item.get("name", ""),
        resource_category=resource_item.get("category", ""),
        resource_unit=resource_item.get("unit", ""),
        resource_description=resource_item.get("intro", ""),
        factor_list=factor_list_str,
    )

    llm = LLMWrapper()
    resp = (llm.generate_response(prompt) or "").strip().strip('"').strip("'")

    for f in cef_list:
        if str(f["id"]) == resp:
            save_cef_result_to_cache(cache, cache_key, resp)
            save_cef_cache(cache, CEF_CACHE_FILE)
            return resp

    return None



# ======================
# Shared: Constructing token / prompt
# ======================

def _build_risk_prompt_and_tokens(
    project_info: str,
    resource_item: Dict[str, Any],
    cef_list: List[Dict[str, Any]],
):
    """
    Map factor list to a,b,c... tokens, and construct RISK_PROMPT.
    Returns: prompt, token_list, token2id, id2token
    """
    ef_ids = [str(f["id"]) for f in cef_list]
    token_list = [chr(ord('a') + i) for i in range(len(cef_list))]
    id2token = dict(zip(ef_ids, token_list))
    token2id = dict(zip(token_list, ef_ids))

    factor_list_str = "\n".join([
        f"{token_list[i]}) EF_ID={f['id']} "
        f"name={f['name']} unit={f['unit']} intro={f['intro']} "
        f"amount={f['amount']} time={f['period']} region={f['region']}"
        for i, f in enumerate(cef_list)
    ])
    candidate_tokens = ", ".join(token_list)

    prompt = RISK_PROMPT.format(
        project_info=project_info,
        resource_name=resource_item.get("resource_name", ""),
        resource_category=resource_item.get("category", ""),
        resource_unit=resource_item.get("unit", ""),
        resource_description=resource_item.get("intro", ""),
        factor_list=factor_list_str,
        candidate_tokens=candidate_tokens,
    )

    return prompt, token_list, token2id, id2token


# =========================
# Mode: cost (original risk control mode)
# =========================

def llm_cost_and_risk(
    project_info: str,
    resource_item: Dict[str, Any],
    cef_list: List[Dict[str, Any]],
    carbon_price: float = 60.0,
    penalty_multiplier: float = 3.0,
    sse_callback=None  # Add optional SSE callback parameter
) -> Optional[Dict[str, Any]]:
    """
    Mode: cost
    Using LLM logits + asymmetric risk loss function to minimize expected economic loss.
    """

    llm = LLMWrapper(sse_callback=sse_callback)  # Pass SSE callback to LLMWrapper

    prompt, token_list, token2id, id2token = _build_risk_prompt_and_tokens(
        project_info, resource_item, cef_list
    )

    token_probs = llm.generate_prob(prompt)
    if not token_probs:
        return None

    top_logprobs = token_probs[0].get("top_logprobs", [])

    logits: Dict[str, float] = {}
    for entry in top_logprobs:
        tok = entry["token"]
        if tok in token_list:
            logits[tok] = entry["logprob"]

    for tok in token_list:
        if tok not in logits:
            logits[tok] = -1e9

    logit_values = np.array([logits[t] for t in token_list], dtype=float)
    exp_vals = np.exp(logit_values - np.max(logit_values))
    softmax_vals = exp_vals / exp_vals.sum()
    probs = {t: float(p) for t, p in zip(token_list, softmax_vals)}

    # E(ef) — Here we assume amount is the emission factor value
    E = {
        str(f["id"]): float(f.get("amount", 0.0))
        for f in cef_list
    }

    P_CO2 = carbon_price
    ETA = penalty_multiplier

    expected_loss: Dict[str, float] = {}

    for t_m in token_list:
        ef_m = token2id[t_m]
        Em = E[ef_m]
        loss_sum = 0.0

        for t_mp in token_list:
            ef_mp = token2id[t_mp]
            Emp = E[ef_mp]
            p_mp = probs[t_mp]

            if Em >= Emp:
                L = P_CO2 * (Em - Emp)
            else:
                L = ETA * P_CO2 * (Emp - Em)

            loss_sum += p_mp * L

        expected_loss[t_m] = loss_sum

    best_token = min(expected_loss, key=expected_loss.get)
    best_id = token2id[best_token]
    best_expected_loss = expected_loss[best_token]

    max_prob_token = max(probs, key=probs.get)
    max_prob_expected_loss = expected_loss[max_prob_token]

    return {
        "best_id": best_id,
        "best_token": best_token,
        "best_expected_loss": best_expected_loss,
        "max_prob_token": max_prob_token,
        "max_prob_id": token2id[max_prob_token],
        "max_prob_expected_loss": max_prob_expected_loss,
        "probabilities": probs,
        "expected_losses": expected_loss,
    }


# =========================
# New: prob / avg / max_ef three modes
# =========================

def llm_prob_and_ef(
    project_info: str,
    resource_item: Dict[str, Any],
    cef_list: List[Dict[str, Any]],
    sse_callback=None  # Add optional SSE callback parameter
) -> Optional[Dict[str, Any]]:
    """
    Unify the softmax probabilities output by LLM and EF values,
    for sharing among prob / avg / max_ef three modes.
    """
    llm = LLMWrapper(sse_callback=sse_callback)  # Pass SSE callback to LLMWrapper

    prompt, token_list, token2id, id2token = _build_risk_prompt_and_tokens(
        project_info, resource_item, cef_list
    )

    token_output = llm.generate_prob(prompt)
    if not token_output:
        return None

    top_logprobs = token_output[0].get("top_logprobs", [])

    logits = {t: -1e9 for t in token_list}
    for entry in top_logprobs:
        tok = entry["token"]
        if tok in logits:
            logits[tok] = entry["logprob"]

    logit_values = np.array([logits[t] for t in token_list], dtype=float)
    exp_vals = np.exp(logit_values - np.max(logit_values))
    probs_arr = exp_vals / exp_vals.sum()
    probs = {t: float(p) for t, p in zip(token_list, probs_arr)}

    E = {str(f["id"]): float(f.get("amount", 0.0)) for f in cef_list}

    return {
        "token_list": token_list,
        "token2id": token2id,
        "id2token": id2token,
        "probabilities": probs,
        "ef_values": E,
    }


# ======================================
# Main entry: find_best_factor (6 parallel modes)
# ======================================

def find_best_factor(
    project_info: str,
    resource_item: Dict[str, Any],
    mode: Mode = "similarity",
    carbon_price: float = 60.0,
    penalty_multiplier: float = 3.0,
    sse_callback=None  # Add optional SSE callback parameter
) -> Optional[Dict[str, Any]]:
    """
    Six modes:
    - similarity: Top-1 by similarity
    - rerank: LLM selects factor
    - cost: Minimum expected loss (includes carbon price + penalty)
    - prob: Factor with highest probability
    - avg: Probability × EF weighted average (returns an expected value)
    - max_ef: Factor with highest EF
    """

    cef_list = get_candidate_factors(resource_item)
    if not cef_list:
        return None

    # Fast path when there's only one candidate
    if len(cef_list) == 1:
        f = dict(cef_list[0])
        amount = _safe_float(f.get("amount"))
        ef_id = str(f.get("id"))

        if mode in ("similarity", "rerank", "prob", "max_ef", "cost"):
            f["mode"] = mode
            f["final_score"] = 1.0
            return f

        if mode == "avg":
            return {
                "mode": "avg",
                "expected_value": amount,
                "probabilities": {ef_id: 1.0},
                "ef_values": {ef_id: amount},
            }

    # Normalize similarity, used for similarity / rerank
    sim_norm = _minmax_norm([_safe_float(c.get("similarity")) for c in cef_list])
    sim_map = {str(c["id"]): s for c, s in zip(cef_list, sim_norm)}

    # ---------- Mode: rerank ----------
    if mode == "rerank":
        best_id = llm_pick_best(project_info, resource_item, cef_list)
        if best_id:
            for f in cef_list:
                if str(f["id"]) == best_id:
                    f = dict(f)
                    f["final_score"] = sim_map.get(str(f["id"]), 0.0)
                    f["mode"] = "rerank"
                    return f
        return None

    # ---------- Mode: cost (original risk decision) ----------
    if mode == "cost":
        result = llm_cost_and_risk(
            project_info, resource_item, cef_list,
            carbon_price=carbon_price,
            penalty_multiplier=penalty_multiplier,
            sse_callback=sse_callback  # Pass SSE callback parameter
        )
        if not result:
            return None

        best_id = result["best_id"]
        for f in cef_list:
            if str(f["id"]) == best_id:
                f = dict(f)
                f["mode"] = "cost"
                f["expected_loss"] = result["best_expected_loss"]
                f["cost_4_max_prob"] = result["max_prob_expected_loss"]
                f["probabilities"] = result["probabilities"]
                f["probabilities"] = result["probabilities"]
                return f
        return None

    # ---------- New Modes: prob / avg / max_ef ----------
    if mode in ("prob", "avg", "max_ef"):
        common = llm_prob_and_ef(project_info, resource_item, cef_list, sse_callback=sse_callback)  # Pass SSE callback
        if not common:
            return None

        token_list = common["token_list"]
        token2id = common["token2id"]
        id2token = common["id2token"]
        probs = common["probabilities"]
        ef_values = common["ef_values"]

        # 1) Factor with highest probability
        if mode == "prob":
            best_token = max(probs, key=probs.get)
            best_id = token2id[best_token]
            for f in cef_list:
                if str(f["id"]) == best_id:
                    f = dict(f)
                    f["mode"] = "prob"
                    f["selected_prob"] = probs[best_token]
                    f["probabilities"] = probs
                    f["token_list"] = token_list
                    f["token2id"] = token2id
                    f["id2token"] = id2token
                    return f
            return None

        # 2) Probability × EF weighted average (returns expected value, no ID selected)
        if mode == "avg":
            # Instead of pre-calculating expected_value, return probabilities and high-probability factors
            # Filter to factors with probability > 0.01
            high_prob_factors = []
            for t in token_list:
                if probs.get(t, 0) > 0.01:
                    ef_id = token2id.get(t)
                    # Find corresponding factor in cef_list
                    for f in cef_list:
                        if str(f.get("id")) == str(ef_id):
                            factor_with_prob = dict(f)
                            factor_with_prob["probability"] = probs[t]
                            high_prob_factors.append(factor_with_prob)
                            break

            return {
                "mode": "avg",
                "probabilities": probs,
                "high_prob_factors": high_prob_factors
            }

        # 3) Factor with highest EF (but only among factors with probability > 0.1)
        if mode == "max_ef":
            # Filter to only consider factors with probability > 0.1
            valid_ef_ids = [token2id[t] for t in token_list if probs.get(t, 0) > 0.1]
            
            if valid_ef_ids:
                # Find the factor with highest EF value among valid factors
                max_ef_id = max(valid_ef_ids, key=lambda ef_id: ef_values.get(ef_id, 0))
                for f in cef_list:
                    if str(f["id"]) == max_ef_id:
                        f = dict(f)
                        f["mode"] = "max_ef"
                        f["selected_probability"] = probs.get(id2token.get(max_ef_id, ''), 0)
                        return f
            
            # If no valid factors found, fall back to overall maximum
            max_ef_id = max(ef_values, key=ef_values.get)
            for f in cef_list:
                if str(f["id"]) == max_ef_id:
                    f = dict(f)
                    f["mode"] = "max_ef"
                    f["selected_probability"] = probs.get(id2token.get(max_ef_id, ''), 0)
                    return f
                    
            return None

    # ---------- Default: similarity ----------
    def sort_key(f: Dict[str, Any]):
        return (
            sim_map.get(str(f["id"]), 0.0),
            get_recent_year(f.get("period"))
        )

    best = max(cef_list, key=sort_key)
    best = dict(best)
    best["final_score"] = sim_map.get(str(best["id"]), 0.0)
    best["mode"] = "similarity"
    return best