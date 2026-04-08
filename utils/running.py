import os
import csv
import json
import logging
from pathlib import Path
import time
from typing import Dict, Any, List, Optional, Tuple, Callable

from configs.neo4j_wrapper import Neo4jWrapper
from configs.llm_wrapper import LLMWrapper
from utils.information_enhancement import enhance_information
from utils.internet_search import create_universal_internet_agent
from utils.utils import (
    _coerce_float,
    _extract_resource_base_value,
    _iter_sub_item_works,
    _normalize_co2_unit,
    _safe_get,
    _to_tons,
    check_fix_wbs,
)
from utils.utils import extract_csv_list
from utils.extract_information import InformationExtractor
from knowledge_graph.cef.get_relationship import find_best_factor
from utils.unit_transfer import unit_transfer_llm, compile_safe_lambda
from prompts import FINAL_RERANK_PROMPT
from knowledge_graph.quota.query import agent_based_query, query as plain_query
from utils import family_group_processor
from utils.quota_cache import (
    load_name_based_cache,
    save_name_based_cache,
    get_cached_quota_result,
    save_quota_result_to_cache,
)


# ------------- logger setting -------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


class CarbonEmissionEngine:
    """
    High-level engine that encapsulates the full carbon-emission workflow.

    Major steps:
        Step 1: Information extraction (WBS parsing & enhancement)
        Step 2: Engineering information completion & KG alignment
        Step 3: Carbon emission factor matching
        Step 4: Emission calculation & hierarchical aggregation

    Features:
        - Optional SSE callback for progress streaming
        - Unified logging via logger.info
        - All key strategy knobs are exposed as constructor arguments
    """

    def __init__(
        self,
        project_file: str,
        project_name: str,
        extraction_cache_dir: str,
        result_dir: str,
        *,
        # Step 1
        enhance_s1: bool = False,
        enhance_s2: bool = False,
        # Step 2
        agent_query: bool = False,
        member_add: bool = False,
        use_reranker: bool = True,
        k: int = 10,
        max_steps: int = 5,
        max_backtracks: int = 5,
        mem_info: bool = True,
        mem_unit: bool = True,
        # Step 3 & 4
        alignment_mode: str = "cost",
        # Transport step toggle
        enable_transport: bool = True,
        # External components
        llm_wrapper = None,
        neo4j_wrapper = None,
        # Optional SSE callback
        sse_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        # Logger
        logger_instance: Optional[logging.Logger] = None,
    ):
        """
        Initialize the engine with file paths, strategy parameters and optional
        external dependencies.
        """

        self.project_file = project_file
        self.extraction_cache_dir = Path(extraction_cache_dir)
        self.extraction_cache_dir.mkdir(parents=True, exist_ok=True)

        self.result_dir = Path(result_dir)
        self.result_dir.mkdir(parents=True, exist_ok=True)

        self.project_name = project_name

        # strategy knobs
        self.enhance_s1 = enhance_s1
        self.enhance_s2 = enhance_s2
        self.agent_query = agent_query
        self.member_add = member_add
        self.use_reranker = use_reranker
        self.k = k
        self.max_steps = max_steps
        self.max_backtracks = max_backtracks
        self.mem_info = mem_info
        self.mem_unit = mem_unit
        self.alignment_mode = alignment_mode
        self.enable_transport = enable_transport

        # Add calculation_time attribute
        self._calculation_time = None

        # step-level cache
        self.step2_cache = self.result_dir / "step2_cache.json"

        # dependencies
        self.llm_wrapper = llm_wrapper

        self.neo4j_wrapper = neo4j_wrapper

        # optional SSE callback
        self.sse_callback = sse_callback

        # logger
        self.logger = logger_instance or logger

        # in-memory state
        self.project: Optional[Dict[str, Any]] = None
        self.indiviual_projects: Optional[Dict[str, Any]] = None

        # progress state
        self.total_steps = 4
        self.progress = 0



    # ---------------------------------------------------------------------
    # Utility: unified progress reporting
    # ---------------------------------------------------------------------
    def _emit_progress(self, event_type: str, payload: Dict[str, Any]):
        """
        Send progress information to both logger and optional SSE callback.
        """
        self.logger.info("%s | %s", event_type.upper(), json.dumps(payload, ensure_ascii=False))

        if self.sse_callback is not None:
            try:
                #   def sse_callback(event_type, payload): ...
                self.sse_callback(event_type, payload)
            except Exception as e:
                self.logger.warning("SSE callback failed: %s", e)



    def _step_progress(self, step: int, message: str, pct: int):
        """
        Emit a standardized pipeline progress event.

        Args:
            step (int): Current major step number (1–4)
            message (str): Human-readable status message
            pct (int): Progress percentage (0–100)

        Notes:
            - This method wraps `_emit_progress()` to ensure
            consistent SSE payload structure across the pipeline.
            - The frontend typically listens to `event: status`.
        """
        payload = {
            "step": step,
            "total_steps": 4,
            "progress": pct,
            "message": message,
        }
        self._emit_progress("status", payload)

    def _sub_progress(self, step: int, sub_idx: int, total_sub: int, name: str):
        """
        Emit sub-progress within a given step.
        Ensures sub-progress remains inside that step's global % range.
        """
        if total_sub <= 0:
            total_sub = 1

        STEP_RANGES = {
            1: (0, 20),
            2: (20, 55),
            3: (55, 90),
            4: (90, 100),
        }

        start, end = STEP_RANGES.get(step, (0, 100))

        pct = start + (end - start) * (sub_idx / total_sub)

        self._emit_progress("status", {
            "step": step,
            "total_steps": 4,
            "progress": round(pct, 2),
            "message": f"Processing {name}",
            "name": name
        })

    def _substep_percent(self, step, sub_idx, total_sub, res_idx, total_res):
        """
        Compute resource-level percent inside a Step.
        Scales progress correctly within STEP_RANGES.
        """
        STEP_RANGES = {
            1: (0, 20),
            2: (20, 55),
            3: (55, 90),
            4: (90, 100),
        }

        start, end = STEP_RANGES.get(step, (0, 100))

        if total_sub <= 0:
            total_sub = 1
        if total_res <= 0:
            total_res = 1

        sub_fraction = sub_idx / total_sub
        resource_fraction = res_idx / total_res

        pct = start + (end - start) * (sub_fraction + resource_fraction / total_sub)

        return round(pct, 2)



    # ---------------------------------------------------------------------
    # Public API: run 4 major steps
    # ---------------------------------------------------------------------
    def run_all(self) -> Dict[str, Any]:
        """
        Execute the complete 4-step carbon emission workflow.

        This function:
            1. Emits standardized SSE progress events for major steps.
            2. Executes each internal stage sequentially.
            3. Returns the final summary JSON produced by Step 4.

        Notes:
            - Internal sub-steps will emit additional progress events
            inside Step 2 and Step 3 (handled elsewhere).
            - Progress percentages here represent coarse, top-level progress.
        """
        start_time = time.time()

        # Workflow start
        self._emit_progress("workflow", {"message": "Pipeline started"})

        # ------------------------------------------------------------------
        # STEP 1 — Information Extraction
        # ------------------------------------------------------------------
        self._step_progress(1, "Information extraction started", 5)
        self.project = self.information_extraction()
        self._step_progress(1, "Information extraction finished", 20)

        # ------------------------------------------------------------------
        # STEP 2 — Information Completion & Knowledge Graph Alignment
        # ------------------------------------------------------------------
        self._step_progress(2, "Information completion started", 25)
        self.indiviual_projects = self.information_completion()
        self._step_progress(2, "Information completion finished", 55)

        # ------------------------------------------------------------------
        # STEP 3 — Optional Material Transport Augmentation
        # ------------------------------------------------------------------
        if self.enable_transport:
            self._step_progress(3, "Material transport augmentation started", 60)
            self.indiviual_projects = self.add_material_transport()
            self._step_progress(3, "Material transport augmentation finished", 70)

        # ------------------------------------------------------------------
        # STEP 3(+4) — Emission Factor Matching & Quantification
        # ------------------------------------------------------------------
        self._step_progress(3, "Emission factor matching & quantification started", 75)
        self.indiviual_projects = self.emission_quantification()
        self._step_progress(3, "Emission factor matching & quantification finished", 90)

        # ------------------------------------------------------------------
        # STEP 4 — Aggregation & Summary Generation
        # ------------------------------------------------------------------
        self._step_progress(4, "Aggregation started", 95)
        summary = self.aggregation()
        self._step_progress(4, "Aggregation finished", 100)

        # Workflow done
        self._emit_progress("workflow", {"message": "Pipeline completed"})
        
        elapsed_time = time.time() - start_time
        calculation_time = round(elapsed_time, 2)
            
        self._calculation_time = calculation_time

        if isinstance(summary, dict):
            summary["calculation_time"] = calculation_time
            
            try:
                summary_file_path = Path(self.result_dir) / "summary_emission.json"
                if summary_file_path.exists():
                    with open(summary_file_path, 'r', encoding='utf-8') as f:
                        existing_summary = json.load(f)
                    
                    existing_summary["calculation_time"] = calculation_time
                    
                    with open(summary_file_path, 'w', encoding='utf-8') as f:
                        json.dump(existing_summary, f, ensure_ascii=False, indent=2)
                else:
                    with open(summary_file_path, 'w', encoding='utf-8') as f:
                        json.dump(summary, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Failed to update summary_emission.json with calculation time: {e}")

        return summary


    # ---------------------------------------------------------------------
    # STEP 1
    # ---------------------------------------------------------------------
    def information_extraction(self) -> Dict[str, Any]:
        """
        STEP 1: Extract WBS information with caching and optional enhancement.
        """

        project_file = self.project_file
        extraction_cache_dir = str(self.extraction_cache_dir)
        enhance_s1 = self.enhance_s1
        enhance_s2 = self.enhance_s2

        project_name = self.project_name

        enhanced_file_name = f"{project_name}_wbs.json"
        raw_file_name = f"{project_name}_wbs_raw.json"

        enhanced_path = Path(extraction_cache_dir) / enhanced_file_name
        raw_path = Path(extraction_cache_dir) / raw_file_name

        # 1) Use cached enhanced WBS if exists
        if enhanced_path.exists():
            self.logger.info("Using cached enhanced WBS: %s", enhanced_path)
            with open(enhanced_path, "r", encoding="utf-8") as f:
                project = json.load(f)
            return project

        # 2) Raw cache exists: only run enhancement
        if raw_path.exists():
            self.logger.info("Found raw WBS cache (%s), enhancing to full WBS...", raw_path)
            project = enhance_information(
                raw_path,
                enhanced_path,
                use_llm_stage1=enhance_s1,
                use_llm_stage2=enhance_s2,
            )
            return project

        # 3) No cache: extract from source, save raw, then enhance
        self.logger.info("Extracting WBS from source file: %s", project_file)
        extractor = InformationExtractor()
        wbs_root = extractor.extract(source=project_file, output_dir=raw_path.parent)

        wbs_root = check_fix_wbs(wbs_root)
        project_dict = wbs_root.model_dump()

        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(project_dict, f, ensure_ascii=False, indent=2)

        self.logger.info("Enhancing WBS → %s", enhanced_path)
        project = enhance_information(
            raw_path,
            enhanced_path,
            use_llm_stage1=enhance_s1,
            use_llm_stage2=enhance_s2,
        )

        return project

    # ---------------------------------------------------------------------
    # STEP 2
    # ---------------------------------------------------------------------
    def information_completion(self) -> Dict[str, Any]:
        """
        STEP 2:
        - Memory-aware quota matching (using name-based cache)
        - Resource retrieval from KG
        - Unit conversion
        - Optional family-group supplementation
        """
        # ===== LLM call statistics =====
        llm_call_stats = {
            "total_llm_calls": 0,
            "by_sub_item": []
        }

        result_dir = Path(self.result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)
        llm_call_file = result_dir / "llm_calls_step2.json"

        project = self.project
        driver = self.neo4j_wrapper.get_driver()
        llm_wrapper = self.llm_wrapper
        step2_cache = self.step2_cache
        agent_query = self.agent_query
        member_add = self.member_add
        use_reranker = self.use_reranker
        k = self.k
        max_steps = self.max_steps
        max_backtracks = self.max_backtracks
        use_memory = self.mem_info

        name_based_cache, cache_meta = load_name_based_cache()

        # Count total sub-item works for progress tracking inside Step 2
        all_sub_items = list(_iter_sub_item_works(project))
        total_sub_items = len(all_sub_items)

        # Check for detailed_tree.json first
        detailed_tree_path = self.result_dir / "detailed_tree.json"
        loaded_from_detailed_tree = False
        if detailed_tree_path.exists():
            try:
                with detailed_tree_path.open("r", encoding="utf-8") as f:
                    indiviual_projects = json.load(f)
                self.logger.info("[STEP 2] Loaded from detailed tree: %s", detailed_tree_path)
                loaded_from_detailed_tree = True
            except Exception as e:
                self.logger.warning("[STEP 2] Failed to load or parse detailed tree: %s", e)
        elif step2_cache.exists() and step2_cache.stat().st_size > 100:
            with step2_cache.open("r", encoding="utf-8") as f:
                indiviual_projects = json.load(f)
            self.logger.info("[STEP 2] Loaded from step cache: %s", step2_cache)
        else:
            self.logger.info("[STEP 2] No step cache found → beginning retrieval and unit conversion.")
            indiviual_projects = project or {}


        neo4j_wrapper = self.neo4j_wrapper

        if agent_query:
            query_agent = agent_based_query.AgentBasedQuery(
                neo4j_wrapper=neo4j_wrapper,
                llm_wrapper=llm_wrapper,
                use_reranker=use_reranker,
                k=k,
            )
        else:
            query_agent = None

        # Iterate through all sub-item works
        for idx, (
            indiviual_project,
            unit_project,
            sub_divisional_work,
            specialty_subdivision,
            sub_item_work,
            root_project,
        ) in enumerate(_iter_sub_item_works(indiviual_projects)):

            # Emit progress for Step 2 internal sub-step
            # This uses the helper `_sub_progress(step, index, total, name)`
            
            sub_name = sub_item_work.get("name", "Unknown Sub-item")
            self._sub_progress(2, idx, total_sub_items, sub_name)

            name = sub_item_work.get("name")
            description = sub_item_work.get("description")
            unit = sub_item_work.get("unit") or ""
            quantity = sub_item_work.get("quantity") or 0
            query_text = f"name:{name},description:{description},unit:{unit},quantity:{quantity}"


            if "resource_items" in sub_item_work and sub_item_work["resource_items"]:
                self.logger.info("[STEP 2] Using existing resource_items for sub-item: %s", name)
                continue

            # Small progress hint
            # Step 2-A: memory-based cache lookup
            cached = get_cached_quota_result(
                name_based_cache,
                cache_meta,
                name=name,
                project_info=query_text,
                llm_wrapper=llm_wrapper,
            )

            if not use_memory:
                cached = None

            if cached:
                best_item, resource_items = cached
            else:
                # Step 2-B: no valid memory → regular matching
                if agent_query and query_agent is not None:
                    best_item, resource_items, llm_calls = query_agent.query(
                        query_input=query_text,
                        use_reranker=use_reranker,
                        max_steps=max_steps,
                        max_backtracks=max_backtracks,
                    )

                    # ===== record llm calls =====
                    llm_call_stats["total_llm_calls"] += llm_calls
                    llm_call_stats["by_sub_item"].append({
                        "sub_item_name": name,
                        "query_text": query_text,
                        "llm_calls": llm_calls,
                    })



                    if not best_item:
                        self.logger.warning(
                            "Agent failed to find quota candidate: %s", query_text
                        )
                        continue
                else:
                    quota_items = []
                    try:
                        quota_items = plain_query.local_semantic_search(
                            driver=driver,
                            node_type="sub_item_work",
                            query_text=query_text,
                            top_k=5,
                        ) or []
                    except Exception as e:
                        self.logger.warning("local_semantic_search failed: %s", e)

                    if not quota_items:
                        self.logger.warning("No quota candidates found: %s", query_text)
                        continue

                    # prompt = FINAL_RERANK_PROMPT.format(
                    #     query_info=query_text,
                    #     sub_items=json.dumps(quota_items, ensure_ascii=False),
                    # )

                    # try:
                    #     resp = llm_wrapper.generate_response(prompt) or ""
                    # except Exception as e:
                    #     self.logger.warning("LLM rerank failed: %s", e)
                    #     resp = ""

                    # ids = extract_csv_list(resp)
                    # best_item = (
                    #     plain_query.find_item_by_id(quota_items, ids[0])
                    #     if ids
                    #     else quota_items[0]
                    # )

                    best_item = quota_items[0]

                    try:
                        resource_items = plain_query.get_resource_items(
                            driver=driver, sub_item_work_node=best_item, project_info=query_text
                        ) or []
                    except Exception as e:
                        self.logger.warning("get_resource_items failed: %s", e)
                        resource_items = []

                # Step 2-C: save new result into memory-based cache
                if use_memory:
                    save_quota_result_to_cache(
                        cache=name_based_cache,
                        meta=cache_meta,
                        name=name,
                        best_item=best_item,
                        resource_items=resource_items,
                    )

            # Step 2-D: unit conversion for the sub-item
            sub_item_work = self.process_sub_item_work_unit_conversion(
                sub_item_work=sub_item_work,
                best_item=best_item,
                resource_items=resource_items,
                project_info=name,
            )

        # Save updated memory-based cache
        if use_memory:
            save_name_based_cache(name_based_cache, cache_meta)

        # ===== write llm call statistics =====
        try:
            with llm_call_file.open("w", encoding="utf-8") as f:
                json.dump(llm_call_stats, f, ensure_ascii=False, indent=2)
            self.logger.info(
                "[STEP 2] LLM call statistics saved to %s (total=%d)",
                llm_call_file,
                llm_call_stats["total_llm_calls"],
            )
        except Exception as e:
            self.logger.warning("Failed to write LLM call statistics: %s", e)


        # Optional: family-group supplementation
        if member_add:
            sub_item_works_with_quota = []
            processed_families = set()

            for (_, _, _, _, sub_item_work, _) in _iter_sub_item_works(indiviual_projects):
                quota_id = sub_item_work.get("matched_quota", {}).get("id")
                if quota_id:
                    sub_item_works_with_quota.append(
                        {
                            "sub_item_work": sub_item_work,
                            "quota_id": quota_id,
                        }
                    )

            family_groups = {}
            for item in sub_item_works_with_quota:
                quota_id = item["quota_id"]
                family_group = family_group_processor.process_family_group(
                    quota_id,
                    sub_item_works_with_quota,
                    neo4j_wrapper,
                    processed_families,
                    plain_query,
                )

                if family_group and family_group["family_id"] not in family_groups:
                    family_groups[family_group["family_id"]] = family_group

            missing_items = family_group_processor.analyze_family_groups(
                family_groups,
                indiviual_projects,
                llm_wrapper,
            )

            family_group_processor.handle_missing_items(
                missing_items,
                indiviual_projects,
                neo4j_wrapper,
            )

        # Save to appropriate cache file
        if loaded_from_detailed_tree:
            detailed_tree_path = self.result_dir / "detailed_tree.json"
            with detailed_tree_path.open("w", encoding="utf-8") as f:
                json.dump(indiviual_projects, f, ensure_ascii=False, indent=2)
            self.logger.info("[STEP 2] Saved updated data to %s", detailed_tree_path)
        else:
            with step2_cache.open("w", encoding="utf-8") as f:
                json.dump(indiviual_projects, f, ensure_ascii=False, indent=2)
            self.logger.info("[STEP 2] Saved step cache to %s", step2_cache)

        return indiviual_projects

    # ---------------------------------------------------------------------
    # STEP 3 & 4 - Emission quantification
    # ---------------------------------------------------------------------
    def emission_quantification(self) -> Dict[str, Any]:
        """
        STEP 3 & 4: Carbon emission quantification for all resource items.

        This method:
            - Selects best emission factors
            - Converts units for denominator alignment
            - Computes carbon emissions
            - Optional: transport emissions
            - Emits detailed SSE progress for:
                • Sub-item level
                • Resource item level
        """

        # Check if detailed_tree.json exists and use it as data source if available
        detailed_tree_path = self.result_dir / "detailed_tree.json"
        if detailed_tree_path.exists():
            try:
                with detailed_tree_path.open("r", encoding="utf-8") as f:
                    indiviual_projects = json.load(f)
                self.logger.info("[STEP 3] Using detailed_tree.json as data source: %s", detailed_tree_path)
            except Exception as e:
                self.logger.warning("[STEP 3] Failed to load detailed_tree.json, falling back to step2 data: %s", e)
                indiviual_projects = self.indiviual_projects
        else:
            indiviual_projects = self.indiviual_projects

        alignment_mode = self.alignment_mode
        use_memory = self.mem_unit

        if indiviual_projects is None:
            raise ValueError("indiviual_projects is not initialized, please run Step 2 first.")

        project_info = (
            f"name: {indiviual_projects.get('name', '')}, "
            f"description: {indiviual_projects.get('description', '')}"
        )

        # -----------------------------------------------------------
        # Step 3: preparation for cost mode
        # -----------------------------------------------------------
        if alignment_mode == "cost":
            try:
                agent = create_universal_internet_agent()
                task = (
                    "Find the current carbon price and penalty multiplier for underreported "
                    f"carbon emissions in {project_info}."
                )
                output_format = (
                    "{"
                    "\"carbon_price\": <number>, "
                    "\"penalty_multiplier\": <number>, "
                    "\"currency\": \"<currency>\", "
                    "\"source\": \"<url>\""
                    "}"
                )
                result = agent(task=task, output_format=output_format)

                carbon_price = result.get("carbon_price") or result.get("price", 60)
                penalty_multiplier = result.get("penalty_multiplier", 3)

            except Exception as e:
                self.logger.warning("Error getting carbon data: %s", e)
                carbon_price = 60
                penalty_multiplier = 3
        else:
            carbon_price = 60
            penalty_multiplier = 3

        # -----------------------------------------------------------
        # STEP 3 PROGRESS — Count sub-items
        # -----------------------------------------------------------
        all_sub_items = list(_iter_sub_item_works(indiviual_projects))
        total_sub_items = len(all_sub_items)

        # Iterate through all sub-item works WITH PROGRESS
        for sub_idx, (
            indiviual_project,
            unit_project,
            sub_divisional_work,
            specialty_subdivision,
            sub_item_work,
            root_project,
        ) in enumerate(all_sub_items):

            sub_name = sub_item_work.get("name", "Unnamed Sub-item")

            # Emit sub-item progress (Step 3, range 55% → 85%)
            self._sub_progress(3, sub_idx, total_sub_items, sub_name)

            resource_items = sub_item_work.get("resource_items") or []
            sub_item_work_info = (
                f"sub-item work: {sub_item_work.get('name', '')}, "
                f"desc: {sub_item_work.get('description', '')}"
            )

            # -----------------------------------------------------------
            # STEP 3 PROGRESS — Resource-level fine detail
            # -----------------------------------------------------------
            total_resources = len(resource_items)

            # 3.1 handle resource items
            for res_idx, res in enumerate(resource_items):

                # Emit resource internal progress (still Step 3, finer detail)
                res_name = res.get("resource_name") or res.get("name") or "Resource"
                self._emit_progress(
                    "status",
                    {
                        "step": 3,
                        "type": "resource_item",
                        "name": res_name,
                        "progress": self._substep_percent(3, sub_idx, total_sub_items, res_idx, total_resources),
                        "message": f"Processing emission factor for resource: {res_name}"
                    },
                )

                # ------------------ actual EF matching ---------------------
                # Check if best_factor already exists in resource item
                best_factor = res.get("best_factor")
                
                # If not found in resource item, calculate using find_best_factor
                if not best_factor:
                    try:
                        best_factor = find_best_factor(
                            project_info=project_info + sub_item_work_info,
                            resource_item=res,
                            mode=alignment_mode,
                            carbon_price=carbon_price,
                            penalty_multiplier=penalty_multiplier,
                            sse_callback=self.sse_callback,  # Pass the SSE callback
                        )
                    except Exception as e:
                        self.logger.warning("[STEP 3] find_best_factor failed: %s", e)
                        best_factor = None


                res["best_factor"] = best_factor
                res_total_qty = _coerce_float(res.get("value"), 0.0)
                res_unit = res.get("unit") or _safe_get(res, "properties", "unit", default="")

                if not best_factor:
                    res["emission"] = 0.0
                    res["emission_unit"] = "kgCO2"
                    continue

                # Handle different modes of best_factor
                if best_factor.get("mode") == "avg":
                    # For avg mode, we calculate weighted average of all high probability factors
                    total_emission = 0.0
                    total_qty_in_denom = 0.0
                    
                    high_prob_factors = best_factor.get("high_prob_factors", [])
                    if not high_prob_factors:
                        res["emission"] = 0.0
                        res["emission_unit"] = "kgCO2"
                        continue
                        
                    for factor in high_prob_factors:
                        factor_val = _coerce_float(factor.get("amount"), 0.0)
                        factor_unit = factor.get("unit")
                        factor_prob = factor.get("probability", 0.0)
                        
                        to_kg_mult, numerator_unit, denom_unit = _normalize_co2_unit(factor_unit)
                        factor_val_kg_per_denom = factor_val * to_kg_mult

                        # Unit mismatch → convert denominator
                        if denom_unit and denom_unit != res_unit:
                            factor_name = factor.get("name", "Unknown EF")
                            factor_id = factor.get("id", "Unknown ID")
                            additional_context = f"Carbon emission factor: {factor_name} (ID: {factor_id})"

                            tf_str = unit_transfer_llm(
                                project_info=res.get("resource_name"),
                                project_unit=res_unit,
                                target_unit=denom_unit,
                                mode="denominator",
                                additional_context=additional_context,
                                use_memory=use_memory,
                            )
                            tf = compile_safe_lambda(tf_str)

                            try:
                                qty_in_denom = float(tf(res_total_qty))
                            except Exception:
                                qty_in_denom = res_total_qty
                        else:
                            qty_in_denom = res_total_qty

                        total_emission += factor_val_kg_per_denom * qty_in_denom * factor_prob
                    
                    emission_kg = total_emission
                else:
                    # For all other modes, use the amount field
                    factor_val = _coerce_float(best_factor.get("amount"), 0.0)
                    factor_unit = best_factor.get("unit")

                    to_kg_mult, numerator_unit, denom_unit = _normalize_co2_unit(factor_unit)
                    factor_val_kg_per_denom = factor_val * to_kg_mult

                    # Unit mismatch → convert denominator
                    if denom_unit and denom_unit != res_unit:
                        factor_name = best_factor.get("name", "Unknown EF")
                        factor_id = best_factor.get("id", "Unknown ID")
                        additional_context = f"Carbon emission factor: {factor_name} (ID: {factor_id})"

                        tf_str = unit_transfer_llm(
                            project_info=res.get("resource_name"),
                            project_unit=res_unit,
                            target_unit=denom_unit,
                            mode="denominator",
                            additional_context=additional_context,
                            use_memory=use_memory,
                        )
                        tf = compile_safe_lambda(tf_str)

                        try:
                            qty_in_denom = float(tf(res_total_qty))
                        except Exception:
                            qty_in_denom = res_total_qty
                    else:
                        qty_in_denom = res_total_qty

                    emission_kg = factor_val_kg_per_denom * qty_in_denom

                # Check for negative emissions (can happen with certain factors)
                if emission_kg < 0.0:
                    self.logger.warning("[STEP 3] Negative emission detected: %s",
                                       res.get("resource_name") or "")
                res["tf_str"] = tf_str
                res["emission"] = emission_kg
                res["emission_unit"] = "kgCO2"

             # -----------------------------------------------------------
            # 4: transport emissions
            # -----------------------------------------------------------
            transport_info = sub_item_work.get("transport", {})
            if transport_info and isinstance(transport_info, dict):
                transport_value = _coerce_float(transport_info.get("value"), 0.0)
                transport_unit = transport_info.get("unit", "")
                transport_factor = transport_info.get("best_factor")

                if transport_value > 0 and transport_factor:
                    transport_factor_val = _coerce_float(transport_factor.get("amount"), 0.0)
                    transport_emission = transport_value * transport_factor_val

                    # Remove existing Truck entries to prevent duplication
                    resource_items = [res for res in resource_items if res.get("category") != "Transport" or res.get("name") != "Truck"]
                    
                    transport_resource = {
                        "name": "Truck",
                        "resource_name": "Truck",
                        "category": "Transport",
                        "id": "transport",
                        "value": transport_value,
                        "unit": transport_unit,
                        "best_factor": transport_factor,
                        "emission": transport_emission,
                        "emission_unit": "kgCO2",
                    }

                    resource_items.append(transport_resource)
                    
            # Update the resource_items in sub_item_work
            sub_item_work["resource_items"] = resource_items

        return indiviual_projects

    # ---------------------------------------------------------------------
    # STEP 4 - Aggregation
    # ---------------------------------------------------------------------
    def aggregation(self) -> Dict[str, Any]:
        """
        STEP 4: Hierarchical aggregation of carbon emissions.
        Includes fine-grained SSE progress.
        """

        indiviual_projects = self.indiviual_projects
        step2_cache = self.step2_cache
        result_dir = self.result_dir
        summary_out = result_dir / "summary_emission.json"

        if indiviual_projects is None:
            raise ValueError("indiviual_projects is not initialized, please run previous steps.")

        # ----- progress bounds -----
        PASS1_START, PASS1_END = 85, 92
        PASS2_START, PASS2_END = 92, 96
        SAVE_START, SAVE_END = 96, 100

        # Count sub_item_work nodes for progress
        all_subitems = list(_iter_sub_item_works(indiviual_projects))
        total_subitems = len(all_subitems)
        if total_subitems <= 0:
            total_subitems = 1

        # ------------------------------------
        # PASS 1 — per-subitem aggregation
        # ------------------------------------
        for idx, (
            indiviual_project,
            unit_project,
            sub_divisional_work,
            specialty_subdivision,
            sub_item_work,
            root_project,
        ) in enumerate(all_subitems):

            # Emit progress
            pct = PASS1_START + (PASS1_END - PASS1_START) * (idx / total_subitems)
            self._emit_progress("status", {
                "step": 4,
                "total_steps": 4,
                "progress": round(pct, 2),
                "message": f"Aggregating sub-item: {sub_item_work.get('name', '')}",
                "name": sub_item_work.get("name", "")
            })

            material_emission = 0.0
            labor_emission = 0.0
            machinery_emission = 0.0
            transport_emission = 0.0

            for res in (sub_item_work.get("resource_items") or []):
                emission = _coerce_float(res.get("emission"), 0.0)
                category = res.get("category", "")

                if category == "Material":
                    material_emission += emission
                elif category == "Labor":
                    labor_emission += emission
                elif category == "Machinery":
                    machinery_emission += emission
                elif category == "Transport":
                    transport_emission += emission

            total_emission = (
                material_emission + labor_emission + machinery_emission + transport_emission
            )

            sub_item_work.setdefault("properties", {})
            sub_item_work["properties"]["emission_tco2"] = _to_tons(total_emission)
            sub_item_work["properties"]["material_emission_tco2"] = _to_tons(material_emission)
            sub_item_work["properties"]["labor_emission_tco2"] = _to_tons(labor_emission)
            sub_item_work["properties"]["machinery_emission_tco2"] = _to_tons(machinery_emission)
            sub_item_work["properties"]["transport_emission_tco2"] = _to_tons(transport_emission)

        # ------------------------------------
        # PASS 2 — recursive aggregation
        # ------------------------------------

        def _sum_children_emission_t(node: Dict[str, Any]) -> float:
            if not isinstance(node, dict):
                return 0.0

            if node.get("level") == "sub_item_work":
                return _coerce_float(
                    _safe_get(node, "properties", "emission_tco2", default=0.0),
                    0.0,
                )

            total_val = 0.0
            for c in (node.get("children") or []):
                total_val += _sum_children_emission_t(c)

            node.setdefault("properties", {})
            node["properties"]["emission_tco2"] = total_val
            return total_val

        # Count top-level individual projects for progress
        top_nodes = indiviual_projects.get("children", []) or []
        total_top = len(top_nodes) if top_nodes else 1

        total_project_emission_tco2 = 0.0

        for idx, ip in enumerate(top_nodes):
            pct = PASS2_START + (PASS2_END - PASS2_START) * (idx / total_top)
            self._emit_progress("status", {
                "step": 4,
                "total_steps": 4,
                "progress": round(pct, 2),
                "message": f"Aggregating parent node: {ip.get('name', '')}",
                "name": ip.get("name", "")
            })

            total_project_emission_tco2 += _sum_children_emission_t(ip)

        # ------------------------------------
        # SAVE FILES — JSON / CSV / summary
        # ------------------------------------

        # Emit progress for file saving start
        self._emit_progress("status", {
            "step": 4,
            "total_steps": 4,
            "progress": SAVE_START,
            "message": "Writing result files..."
        })

        # Save detailed tree
        detailed_tree_path = result_dir / "detailed_tree.json"
        with detailed_tree_path.open("w", encoding="utf-8") as f:
            json.dump(indiviual_projects, f, ensure_ascii=False, indent=2)

        # Save CSV
        flat_csv_path = result_dir / "subitems.csv"
        with flat_csv_path.open("w", newline="", encoding="utf-8") as fcsv:
            writer = csv.writer(fcsv)
            writer.writerow([
                "single_project_name",
                "unit_project_name",
                "sub_divisional_work_name",
                "specialty_subdivision_name",
                "sub_item_work_name",
                "used_quantity",
                "used_unit",
                "matched_quota_name",
                "emission_tco2",
                "material_emission_tco2",
                "labor_emission_tco2",
                "machinery_emission_tco2",
                "transport_emission_tco2",
            ])

            for (
                indiviual_project,
                unit_project,
                sub_divisional_work,
                specialty_subdivision,
                sub_item_work,
                root_project,
            ) in _iter_sub_item_works(indiviual_projects):

                matched_quota = sub_item_work.get("matched_quota", {}) or {}
                matched_quota_name = _safe_get(matched_quota, "name", default="")

                writer.writerow([
                    _safe_get(indiviual_project, "name", default=""),
                    _safe_get(unit_project, "name", default=""),
                    _safe_get(sub_divisional_work, "name", default=""),
                    _safe_get(specialty_subdivision, "name", default=""),
                    _safe_get(sub_item_work, "name", default=""),
                    _safe_get(sub_item_work, "properties", "used_quantity", default=""),
                    _safe_get(sub_item_work, "properties", "used_unit", default=""),
                    matched_quota_name,
                    _safe_get(sub_item_work, "properties", "emission_tco2", default=0.0),
                    _safe_get(sub_item_work, "properties", "material_emission_tco2", default=0.0),
                    _safe_get(sub_item_work, "properties", "labor_emission_tco2", default=0.0),
                    _safe_get(sub_item_work, "properties", "machinery_emission_tco2", default=0.0),
                    _safe_get(sub_item_work, "properties", "transport_emission_tco2", default=0.0),
                ])

        # Save summary JSON
        summary = {
            "project_total_emission_tco2": total_project_emission_tco2,
            "generated_from": str(step2_cache.name),
            "artifacts": {
                "detailed_tree_json": str(detailed_tree_path.name),
                "flat_csv": str(flat_csv_path.name),
            },
        }

        # Add calculation_time if it exists in the original summary
        if hasattr(self, '_calculation_time'):
            summary["calculation_time"] = self._calculation_time

        with summary_out.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Final 100% event
        self._emit_progress("status", {
            "step": 4,
            "total_steps": 4,
            "progress": 100,
            "completed": True,
            "message": "Aggregation completed"
        })

        return summary

    # ---------------------------------------------------------------------
    # Transport augmentation
    # ---------------------------------------------------------------------
    def add_material_transport(
        self,
        transport_factor: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Add material transportation information between step 2 and step 3/4.

        Updates sub_item_work["transport"] and optionally updates step2 cache.
        """

        if self.indiviual_projects is None:
            raise ValueError("indiviual_projects is not initialized, please run Step 2 first.")

        indiviual_projects = self.indiviual_projects
        step2_cache = self.step2_cache

        if transport_factor is None:
            transport_factor = {
                "id": "40101002",
                "name": "Truck",
                "amount": 0.115,
                "unit": "kgCO2e/(t*km)",
            }

        excluded_material_ids = {
            "RI-Material-974899ef025c",
            "RI-Material-eab619fba24a",
            "RI-Material-36f698265032",
            "RI-Material-d0df03650533",
            "RI-Material-d303ebcee171",
        }

        for (_, _, _, _, sub_item_work, _) in _iter_sub_item_works(indiviual_projects):
            if "transport" in sub_item_work and sub_item_work["transport"]:
                continue

            resource_items = sub_item_work.get("resource_items", [])

            has_valid_material = False
            total_transport_value = 0.0

            for res in resource_items:
                category = res.get("category", "")
                resource_id = res.get("resource_id", "")

                if category == "Material" and resource_id not in excluded_material_ids:
                    has_valid_material = True

                    resource_name = res.get("name", res.get("resource_name", "Unknown Material"))
                    resource_unit = res.get("unit", res.get("properties", {}).get("unit", ""))

                    resource_value = _extract_resource_base_value(res)

                    matched_quota_name = sub_item_work.get("matched_quota", {}).get(
                        "name", "Unknown Quota"
                    )
                    matched_quota_id = sub_item_work.get("matched_quota", {}).get(
                        "id", "Unknown ID"
                    )
                    additional_context = (
                        f"Matched quota: {matched_quota_name} (ID: {matched_quota_id})"
                    )

                    concrete_keywords = ["混凝土", "砼"]
                    is_concrete = any(keyword in resource_name for keyword in concrete_keywords)
                    actual_transport_distance = 40.0 if is_concrete else 500.0

                    try:
                        transfer_func_str = unit_transfer_llm(
                            project_info=resource_name,
                            project_unit=resource_unit,
                            target_unit="t",
                            mode="material_transport",
                            additional_context=additional_context,
                            use_memory=self.mem_unit,
                        )

                        transfer_func = compile_safe_lambda(transfer_func_str)
                        value_in_ton = float(transfer_func(resource_value))

                        total_transport_value += value_in_ton * actual_transport_distance

                    except Exception as e:
                        self.logger.warning(
                            "Material transport unit conversion failed %s: %s",
                            resource_name,
                            e,
                        )
                        continue

            if has_valid_material and total_transport_value > 0:
                transport_entry = {
                    "value": total_transport_value,
                    "unit": "t*km",
                    "best_factor": transport_factor,
                }
                sub_item_work["transport"] = transport_entry
            else:
                sub_item_work["transport"] = {}

        if step2_cache is not None:
            try:
                with step2_cache.open("w", encoding="utf-8") as f:
                    json.dump(indiviual_projects, f, ensure_ascii=False, indent=2)
                self.logger.info("Cache file updated with transport: %s", step2_cache)
            except Exception as e:
                self.logger.warning("Failed to update cache file: %s", e)

        return indiviual_projects

    # ---------------------------------------------------------------------
    # Sub-item unit conversion helper
    # ---------------------------------------------------------------------
    def process_sub_item_work_unit_conversion(
        self,
        sub_item_work: Dict[str, Any],
        best_item: Dict[str, Any],
        resource_items: List[Dict[str, Any]],
        project_info: str,
        use_memory: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Perform unit conversion for a sub-item work and compute resource quantities.
        """

        if use_memory is None:
            use_memory = self.mem_unit

        sub_item_work_unit = sub_item_work.get("unit") or ""
        quota_unit = _safe_get(best_item, "properties", "unit", default="")

        quota_name = _safe_get(best_item, "properties", "name", default="Unknown Quota")
        quota_id = _safe_get(best_item, "properties", "id", default="UnknownID")
        additional_context = f"Matched quota: {quota_name} (ID: {quota_id})"

        transfer_func_str = unit_transfer_llm(
            project_info=project_info,
            project_unit=sub_item_work_unit,
            target_unit=quota_unit,
            mode="quantity",
            additional_context=additional_context,
            use_memory=use_memory,
        )
        transfer_func = compile_safe_lambda(transfer_func_str)

        properties = sub_item_work.get("properties", {})
        quantity = _coerce_float(sub_item_work.get("quantity", 0.0), 0.0)

        if sub_item_work_unit and quota_unit and (sub_item_work_unit != quota_unit):
            try:
                converted_quantity = float(transfer_func(quantity))
            except Exception as e:
                self.logger.warning(
                    "Unit conversion failed, falling back to 1:1. Error: %s", e
                )
                converted_quantity = quantity

            properties["transfered_unit"] = quota_unit
            properties["transfered_quantity"] = converted_quantity
            used_quantity, used_unit = converted_quantity, quota_unit
        else:
            used_quantity, used_unit = quantity, sub_item_work_unit

        processed_resources: List[Dict[str, Any]] = []

        for res in (resource_items or []):
            base_val = _extract_resource_base_value(res)
            total_val = base_val * used_quantity

            res["value"] = total_val

            if "unit" not in res:
                ru = _safe_get(res, "properties", "unit")
                if ru:
                    res["unit"] = ru

            processed_resources.append(res)

        sub_item_work["resource_items"] = processed_resources

        sub_item_work.setdefault("matched_quota", {})
        sub_item_work["matched_quota"]["id"] = _safe_get(best_item, "properties", "id")
        sub_item_work["matched_quota"]["name"] = _safe_get(best_item, "properties", "name")

        sub_item_work.setdefault("properties", {})
        sub_item_work["properties"]["used_quantity"] = used_quantity
        sub_item_work["properties"]["used_unit"] = used_unit
        sub_item_work["properties"].update(properties)

        return sub_item_work
