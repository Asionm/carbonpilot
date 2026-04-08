# -*- coding: utf-8 -*-
import logging
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import StateGraph, END, START

from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper
from knowledge_graph.quota.query import query as vector_query
from prompts import (
    VECTOR_RERANK_PROMPT,
    NODE_SELECTION_PROMPT,
    SUB_ITEM_CHECK_PROMPT,
    FINAL_RERANK_PROMPT,
)
from utils.utils import extract_csv_list

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ========= State =========
class ExplorationState(TypedDict, total=False):
    current_node: Optional[Dict[str, Any]]
    path_history: List[Dict[str, Any]]
    visited_nodes: List[str]        
    blocked_nodes: List[str]   
    candidate_nodes: List[Dict[str, Any]]
    final_items: List[Dict[str, Any]]  
    rejected_items: List[Dict[str, Any]]  
    best_item: Optional[Dict[str, Any]]   
    query_input: Dict[str, Any]
    max_steps: int
    max_backtracks: int
    steps: int
    backtracks: int
    node_id_key: str
    node_name_key: str
    _should_end: bool
    llm_calls: int


@dataclass
class AgentBasedQuery:
    neo4j_wrapper: Neo4jWrapper
    llm_wrapper: LLMWrapper
    k: int = 10  
    use_reranker: bool = False  
    vector_aug_k: int = 3
    query_text: str = ""       


    def __post_init__(self):
        self.driver = self.neo4j_wrapper.get_driver()


    @staticmethod
    def _normalize_node(raw: Dict[str, Any], id_key: str = "id", name_key: str = "name") -> Dict[str, Any]:

        labels = raw.get("labels") or raw.get("label") or []
        props = raw.get("properties") or {}
        nid = props.get(id_key) or raw.get("id") or props.get("uuid") or "unknown"
        name = props.get(name_key) or raw.get("name") or props.get("title") or ""
        return {
            "id": nid,
            "name": name,
            "labels": labels if isinstance(labels, list) else [labels],
            "properties": props,
        }

    @staticmethod
    def _safe_float(text: str, default: float = 0.0) -> float:
        try:
            m = re.search(r"([0-9]*\.?[0-9]+)", text)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return default


    def _call_llm(self, prompt: str, state: Optional[ExplorationState] = None) -> str:
        """
        Wrapper for LLM calls that counts usage.
        """
        if state is not None:
            state["llm_calls"] = state.get("llm_calls", 0) + 1
        return self.llm_wrapper.generate_response(prompt)

    def vector_retrieval_and_rerank(self, query_text: str, state: ExplorationState, id_key: str = "id", name_key: str = "name") -> List[Dict[str, Any]]:

        raw = vector_query.global_semantic_search(self.driver, query_text, top_k=self.k, exclude_labels=["resource_item", "Factor"]) or []

        local_results = vector_query.local_semantic_search(self.driver, "sub_item_work", query_text, top_k=5) or []

        existing_ids = {item.get("id") for item in raw if item.get("id")}
        for local_result in local_results:
            local_props = local_result.get("properties", {})
            local_id = local_props.get("id")
            if local_id and local_id not in existing_ids:
                raw.append(local_result)
                existing_ids.add(local_id)

        cleaned_map = {}

        for c in raw:
            node = self._normalize_node(c, id_key, name_key)
            node_id = node.get("id")
            if not node_id:
                continue

            props = node.get("properties") or {}
            sim = c.get("score") or c.get("similarity") or props.get("similarity")

            item = {
                "id": node_id,
                "name": node.get("name"),
                "labels": node.get("labels"),
                "properties": props,
            }

            cleaned_map[node_id] = item

        cleaned = list(cleaned_map.values())

        if not self.use_reranker:
            return sorted(cleaned, key=lambda x: x.get("similarity", 0), reverse=True)

        candidates_json = json.dumps(cleaned, ensure_ascii=False)
        prompt = VECTOR_RERANK_PROMPT.format(query_text=query_text, candidates=candidates_json)
        resp = self._call_llm(prompt, state) or ""
        order = extract_csv_list(resp)

        idx = {id_: i for i, id_ in enumerate(order)}
        reranked = sorted(cleaned, key=lambda x: idx.get(x["id"], 10**9))
        return reranked


    def is_sub_item_work(self, node: Dict[str, Any]) -> bool:
        labels = node.get("labels") or []
        return "sub_item_work" in labels

    def evaluate_sub_item_fit(
        self,
        node: Dict[str, Any],
        query_input: Dict[str, Any],
        state: ExplorationState
    ) -> Dict[str, Any]:

        node_payload = {
            "id": node.get("id"),
            "name": node.get("name"),
            "labels": node.get("labels", []),
            "properties": node.get("properties", {}),
        }

        prompt = SUB_ITEM_CHECK_PROMPT.format(
            query_info=json.dumps(query_input, ensure_ascii=False),
            node_info=json.dumps(node_payload, ensure_ascii=False),
        )

        resp = (self._call_llm(prompt, state) or "").strip()

        result = {
            "node_id": node.get("id"),
            "score": 0.0,
            "is_match": False,
            "reason": resp[:200],
            "fuzzy_matrix": None,
        }

        try:
            data = json.loads(resp)
            if isinstance(data, dict):
                result["node_id"] = data.get("node_id", result["node_id"])
                result["reason"] = str(data.get("reason", result["reason"]))[:200]
                result["fuzzy_matrix"] = data.get("fuzzy_matrix")
        except Exception:
            return result


        fuzzy_matrix = result.get("fuzzy_matrix")
        if not isinstance(fuzzy_matrix, dict):
            return result


        weights = {
            "name": 0.33,
            "feature": 0.33,
            "unit": 0.33,
        }


        grade_values = {
            "highly_suitable": 1.0,
            "moderately_suitable": 0.75,
            "barely_suitable": 0.5,
            "unsuitable": 0.0,
        }

        score = 0.0
        for factor, memberships in fuzzy_matrix.items():
            if factor not in weights or not isinstance(memberships, dict):
                continue

            factor_score = 0.0
            for grade, value in grade_values.items():
                factor_score += memberships.get(grade, 0.0) * value

            score += weights[factor] * factor_score

        score = round(score, 4)

        result["score"] = score
        result["is_match"] = score >= 0.8

        return result

    def free_exploration(self, current_node: Dict[str, Any], state: ExplorationState) -> Optional[Dict[str, Any]]:
        if not current_node:
            return None

        node_id = current_node.get("id")
        node_name = current_node.get("name")
        id_key = state.get("node_id_key", "id")
        name_key = state.get("node_name_key", "name")


        query = f"""
                MATCH (n)-[r]-(neighbor)
                WHERE (
                    n.{id_key} = $node_id
                    OR n.{name_key} = $node_name
                )
                AND NONE(l IN labels(neighbor) WHERE l IN ['resource_item', 'Factor', 'Time', 'Region', 'Source'])
                RETURN neighbor, labels(neighbor) AS labels, type(r) AS rel_type
                LIMIT 10
        """

        neighbors = []
        with self.driver.session() as session:
            result = session.run(query, node_id=node_id, node_name=node_name)
            for record in result:
                raw = record.get("neighbor")
                lab = record.get("labels") or []
                node = self._normalize_node(
                    {"properties": vector_query.prune_props(raw), "labels": lab},
                    id_key=id_key,
                    name_key=name_key
                )
                node["rel_type"] = record.get("rel_type")
                node["__source__"] = "neighbor"  
                neighbors.append(node)


        vector_pool = list(state.get("candidate_nodes", [])) 

        vector_pool = [v for v in vector_pool if v.get("id") != node_id][: self.vector_aug_k]
        for v in vector_pool:
            v = dict(v)
            v.pop("rel_type", None)
            v["__source__"] = "vector"


        visited = set(state.get("visited_nodes", []))
        blocked = set(state.get("blocked_nodes", []))
        rejected_ids = {x.get("id") for x in state.get("rejected_items", [])}

        def _ok(n):
            nid = n.get("id")
            return (nid not in rejected_ids)

        neighbor_cands = [n for n in neighbors if _ok(n)]
        vector_cands = [v for v in vector_pool if _ok(v)]


        combined = neighbor_cands + vector_cands
        if not combined:
            return None


        trail = " -> ".join(
            [x.get("name", x.get("id", "")) for x in state.get("path_history", [])][-6:]
            + [current_node.get("name", current_node.get("id", ""))]
        )

        def _line(n):
            labels = ", ".join(n.get("labels") or [])
            rel = n.get("rel_type") or "-"
            src = n.get("__source__", "?")
            sim = n.get("similarity")
            sim_part = f"; similarity: {sim:.4f}" if isinstance(sim, (int, float)) else ""
            return (
                f"[ID: {n.get('id')}] name: {n.get('name')}; labels: {labels}; "
                f"rel: {rel}; source: {src}{sim_part}"
            )

        cand_lines = "\n".join(_line(n) for n in combined)

        prompt = NODE_SELECTION_PROMPT.format(
            query_info=json.dumps(state.get("query_input", {}), ensure_ascii=False),
            history=trail,
            visited_ids=json.dumps(list(visited), ensure_ascii=False),
            blocked_ids=json.dumps(list(blocked), ensure_ascii=False),
            neighbors=cand_lines,
        )
        resp = (self._call_llm(prompt, state) or "").strip()
        picked = resp.strip().strip('"').strip("'")


        for n in combined:
            if n["id"] == picked or n["name"] == picked:
                return n


        return combined[0] if combined else None


    def backtrack(self, state: ExplorationState) -> ExplorationState:
        state["backtracks"] = state.get("backtracks", 0) + 1
        if state.get("path_history"):
            state["current_node"] = state["path_history"].pop()
        else:
            state["current_node"] = None
        return state
    
    def finalize_and_return(
        self,
        state: ExplorationState
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:


        if state.get("best_item"):
            logger.info(
                f"Direct hit on best_item: {state['best_item'].get('name')}"
            )
            return (
                state["best_item"],
                vector_query.get_resource_items(
                    self.driver,
                    state["best_item"],
                    self.query_text
                ),
                state["llm_calls"],
            )

        rejected = state.get("rejected_items", [])


        if rejected:
            best_fallback = max(
                rejected,
                key=lambda x: x.get("score", 0.0)
            )
            logger.info(
                f"No direct hit. Using highest-score rejected item: "
                f"{best_fallback.get('name')} (score: {best_fallback.get('score')})"
            )
            return (
                best_fallback,
                vector_query.get_resource_items(
                    self.driver,
                    best_fallback,
                    self.query_text
                ),
                state["llm_calls"],
            )


        candidate_nodes = state.get("candidate_nodes", [])
        sub_item_candidates = [
            node for node in candidate_nodes
            if self.is_sub_item_work(node)
        ]

        if sub_item_candidates:
            fallback = sub_item_candidates[0]
            logger.info(
                f"No rejected items found. "
                f"Using first sub_item_work candidate: {fallback.get('name')}"
            )
            return (
                fallback,
                vector_query.get_resource_items(
                    self.driver,
                    fallback,
                    self.query_text
                ),
                state["llm_calls"],
            )


        logger.warning(
            "No best_item, no rejected_items, and no sub_item_work candidates. "
            "Returning empty fallback."
        )

        return (
            {
                "id": "fallback_empty",
                "name": "No matching sub-item found",
                "score": 0.0,
                "reason": "Fallback due to no evaluable sub-item candidates",
                "labels": [],
                "properties": {},
            },
            [],
            state["llm_calls"],
        )

    def _node_vector_retrieval(self, state: ExplorationState) -> ExplorationState:
        q = state.get("query_input") or {}
        query_text = json.dumps(q, ensure_ascii=False)
        self.query_text = query_text
        id_key = state.get("node_id_key", "id")
        name_key = state.get("node_name_key", "name")

        cands = self.vector_retrieval_and_rerank(query_text, state, id_key=id_key, name_key=name_key)
        first = cands[0] if cands else None

        updates: ExplorationState = {
            "candidate_nodes": cands,
            "current_node": first,
        }
        if first:
            updates["visited_nodes"] = list(set(state.get("visited_nodes", []) + [first["id"]]))
        return updates

    def _node_check_sub_item(self, state: ExplorationState) -> ExplorationState:

        node = state.get("current_node")
        if not node:
            return state

        if not self.is_sub_item_work(node):
            return state

        fit = self.evaluate_sub_item_fit(
            node,
            state.get("query_input", {}),
            state
        )

        logger.info(f"Sub-item fit: {node.get('name')} -> {fit}")

        node_with_score = dict(node)
        node_with_score["score"] = float(fit.get("score", 0.0))
        node_with_score["fit_reason"] = fit.get("reason", "")

        if fit.get("is_match"):
            state["best_item"] = node_with_score
            state["_should_end"] = True
        else:
            state.setdefault("rejected_items", []).append(node_with_score)
            state.setdefault("blocked_nodes", []).append(node.get("id"))

        return state

    def _node_check_stop(self, state: ExplorationState) -> ExplorationState:

        if state.get("best_item"):
            state["_should_end"] = True
            logger.info("Best item found. Stopping exploration.")
            return state

        state["steps"] = state.get("steps", 0) + 1
        steps_exceeded = state["steps"] >= state.get("max_steps", 30)
        backtracks_exceeded = state.get("backtracks", 0) >= state.get("max_backtracks", 10)

        if steps_exceeded or backtracks_exceeded:
            reason = []
            if steps_exceeded:
                reason.append(f"steps={state['steps']} >= max_steps={state.get('max_steps')}")
            if backtracks_exceeded:
                reason.append(f"backtracks={state.get('backtracks', 0)} >= max_backtracks={state.get('max_backtracks')}")
            logger.info(f"Exploration stopped due to: {'; '.join(reason)}")
            state["_should_end"] = True
        else:
            state["_should_end"] = False
        return state
    def _node_explore_neighbors(self, state: ExplorationState) -> ExplorationState:

        curr = state.get("current_node")
        if not curr:
            return state

        state.setdefault("path_history", [])
        if not state["path_history"] or state["path_history"][-1].get("id") != curr.get("id"):
            state["path_history"].append(curr)

        next_node = self.free_exploration(curr, state)
        if next_node:
            state.setdefault("visited_nodes", [])
            if next_node["id"] not in state["visited_nodes"]:
                state["visited_nodes"].append(next_node["id"])
            state["current_node"] = next_node
            return state

        state = self.backtrack(state)
        return state

    def _build_graph(self):

        graph = StateGraph(ExplorationState)

        graph.add_node("vector_retrieval", self._node_vector_retrieval)
        graph.add_node("check_sub_item", self._node_check_sub_item)
        graph.add_node("check_stop", self._node_check_stop)
        graph.add_node("explore_neighbors", self._node_explore_neighbors)


        graph.add_edge(START, "vector_retrieval")
        graph.add_edge("vector_retrieval", "check_sub_item")
        graph.add_edge("check_sub_item", "check_stop")

        def route_after_check(state: ExplorationState):
            return "end" if state.get("_should_end") else "continue"

        graph.add_conditional_edges(
            "check_stop",
            route_after_check,
            {"end": END, "continue": "explore_neighbors"},
        )
        graph.add_edge("explore_neighbors", "check_sub_item")

        return graph.compile()


    def query(
            self, 
            query_input: Dict[str, Any], 
            use_reranker: Optional[bool] = None, 
            max_steps: int = 20,
            max_backtracks: int = 20
            ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:

        if use_reranker is not None:
            original_use_reranker = self.use_reranker
            self.use_reranker = use_reranker

        initial_state: ExplorationState = {
            "current_node": None,
            "path_history": [],
            "visited_nodes": [],
            "blocked_nodes": [],
            "candidate_nodes": [],
            "final_items": [],
            "rejected_items": [],
            "best_item": None,
            "query_input": query_input,
            "max_steps": max_steps,
            "max_backtracks": max_backtracks,
            "steps": 0,
            "backtracks": 0,
            "node_id_key": "id",
            "node_name_key": "name",
            "_should_end": False,
            "llm_calls": 0,
        }

        graph = self._build_graph()
        final_state = initial_state

        try:
            final_state = graph.invoke(initial_state, config={"recursion_limit": 50})
        except Exception as e:
            logger.warning(f"Graph execution failed: {e}. Falling back to rejected_items...")

            pass

        item, resource, llm_calls = self.finalize_and_return(final_state)


        if use_reranker is not None:
            self.use_reranker = original_use_reranker

        return item, resource, llm_calls