from __future__ import annotations
import os
import json
import hashlib
import logging
import ast
import re
from typing import Any, Dict, Optional, Callable
from math import exp

from configs.llm_wrapper import LLMWrapper
from prompts import UNIT_TRANSFER_PROMPT

logger = logging.getLogger(__name__)

# ======================================================
# Paths
# ======================================================

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "unit_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UNIT_CACHE_PATH = os.path.join(CACHE_DIR, "unit_conversions_cache.json")
MEMORY_META_PATH = os.path.join(CACHE_DIR, "_unit_memory_meta.json")

# In-memory (not persisted)
_INMEMO_CACHE: Dict[str, str] = {}

# ======================================================
# AST rules for safe lambda
# ======================================================

_ALLOWED_NODES = (
    ast.Expression, ast.Lambda, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
    ast.Load, ast.Name, ast.Num, ast.Constant, ast.Pow, ast.Mod,
    ast.Tuple, ast.List, ast.arguments, ast.arg
)

# ======================================================
# Memory mechanism parameters
# ======================================================

LAMBDA = 0.05
ALPHA = 0.7
STRONG_TH = 0.6
WEAK_TH = 0.2


# ======================================================
# Load static rule-based conversions (priority)
# ======================================================

def _load_unit_conversions():
    json_path = os.path.join(os.path.dirname(__file__), "unit_conversions.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

_UNIT_CONVERSIONS = _load_unit_conversions()


def _get_rule_based_conversion(project_unit: str, target_unit: str) -> Optional[str]:
    conv = _UNIT_CONVERSIONS

    # Step 1: find the physical dimension of each unit
    project_dim = None
    target_dim = None

    for dim, units in conv.items():
        if project_unit in units:
            project_dim = dim
        if target_unit in units:
            target_dim = dim

    # Step 2: only allow rule-based conversion within the same dimension
    if project_dim is None or target_dim is None:
        return None

    if project_dim != target_dim:
        return None

    units = conv[project_dim]

    # Step 3: same-dimension unit conversion
    # base rule: value_in_base = x * units[unit]
    # so: x_project → x_target = x * units[project] / units[target]
    k_project = units[project_unit]
    k_target = units[target_unit]

    if k_target == 0:
        return None

    return f"lambda x: x * {k_project} / {k_target}"



# ======================================================
# Memory metadata (access count / timestamp)
# ======================================================

def _load_memory_meta() -> Dict[str, Any]:
    if os.path.exists(MEMORY_META_PATH):
        try:
            with open(MEMORY_META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"access_count": {}, "last_access": {}}


def _save_memory_meta(meta: Dict[str, Any]) -> None:
    try:
        with open(MEMORY_META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save memory meta: %s", e)


def _reinforce(key: str) -> None:
    meta = _load_memory_meta()
    count = meta["access_count"].get(key, 0) + 1
    meta["access_count"][key] = count
    meta["last_access"][key] = os.path.getmtime(UNIT_CACHE_PATH) if os.path.exists(UNIT_CACHE_PATH) else 0
    _save_memory_meta(meta)


def _compute_strength(key: str, meta: Dict[str, Any]) -> float:
    count = meta["access_count"].get(key, 0)
    last_acc = meta["last_access"].get(key, 0)
    now = os.path.getmtime(UNIT_CACHE_PATH) if os.path.exists(UNIT_CACHE_PATH) else 0
    elapsed = max(0.0, (now - last_acc) / 86400)
    return (ALPHA * count) * exp(-LAMBDA * elapsed)


# ======================================================
# Unified Cache (single JSON file)
# ======================================================

def _mk_cache_key(project_unit: str, target_unit: str, project_info: str, mode: Optional[str]) -> str:
    return hashlib.md5(f"{project_unit}::{target_unit}::{project_info}::{mode or ''}".encode()).hexdigest()


def _load_global_cache() -> Dict[str, Any]:
    """Load the unified JSON cache."""
    if not os.path.exists(UNIT_CACHE_PATH):
        return {}
    try:
        with open(UNIT_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_global_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(UNIT_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save unified unit cache: %s", e)


def _load_from_cache(project_unit: str, target_unit: str, project_info: str, mode: Optional[str]) -> Optional[str]:
    """Load conversion function from unified cache."""
    key = _mk_cache_key(project_unit, target_unit, project_info, mode)

    if key in _INMEMO_CACHE:
        return _INMEMO_CACHE[key]

    cache = _load_global_cache()
    if key in cache:
        tf = cache[key].get("transfer_func")
        if tf:
            _INMEMO_CACHE[key] = tf
        return tf

    return None


def _save_to_cache(
    project_unit: str,
    target_unit: str,
    transfer_func: str,
    project_info: str,
    mode: Optional[str],
    prompt: str,
    reasoning: str
) -> None:

    key = _mk_cache_key(project_unit, target_unit, project_info, mode)

    _INMEMO_CACHE[key] = transfer_func

    cache = _load_global_cache()
    cache[key] = {
        "project_unit": project_unit,
        "target_unit": target_unit,
        "project_info": project_info,
        "mode": mode,
        "transfer_func": transfer_func,
        "prompt": prompt,
        "reasoning": reasoning,
    }

    _save_global_cache(cache)


# ======================================================
# LLM-based Unit Conversion
# ======================================================

def unit_transfer_llm(
    project_info: str,
    project_unit: str,
    target_unit: str,
    mode: Optional[str] = None,
    additional_context: Optional[str] = None,
    use_memory: bool = True
) -> str:

    rule = _get_rule_based_conversion(project_unit, target_unit)
    if rule:
        return rule

    if use_memory:
        cached = _load_from_cache(project_unit, target_unit, project_info, mode)
        if cached:
            _reinforce(_mk_cache_key(project_unit, target_unit, project_info, mode))
            return cached

    llm = LLMWrapper()

    if not additional_context:
        additional_context = "No additional context."
    else:
        additional_context = f"[Related Context]:\n{additional_context}"

    prompt = UNIT_TRANSFER_PROMPT.format(
        project_info=project_info,
        project_unit=project_unit,
        target_unit=target_unit,
        mode=(mode or "default"),
        additional_context=additional_context
    )

    response = llm.generate_response(prompt)

    transfer_func = "lambda x: x"
    reasoning = "No reasoning provided"

    try:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            response_json = json.loads(json_match.group())
            transfer_func = response_json.get("transfer_function", "lambda x: x")
            reasoning = response_json.get("reasoning", "No reasoning")
    except Exception:
        transfer_func = response.strip() or "lambda x: x"

    if use_memory:
        _save_to_cache(
            project_unit, target_unit, transfer_func,
            project_info, mode, prompt, reasoning
        )

    return transfer_func


# ======================================================
# Safe Lambda Compiler
# ======================================================

def _sanitize_lambda_string(s: str) -> str:
    s = s.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


class _SafeChecker(ast.NodeVisitor):
    def visit_Call(self, node: ast.Call) -> None:
        raise ValueError(f"Illegal node: {type(node).__name__}")
    def generic_visit(self, node):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"Illegal syntax node: {type(node).__name__}")
        super().generic_visit(node)


def compile_safe_lambda(func_str: str) -> Callable[[float], float]:
    try:
        func_str = _sanitize_lambda_string(func_str)
        node = ast.parse(func_str, mode="eval")
        _SafeChecker().visit(node)
        code = compile(node, "<safe_lambda>", "eval")
        fn = eval(code, {"__builtins__": None}, {})
        fn(0)  # test run
        return fn
    except Exception as e:
        logger.warning("compile_safe_lambda failed, fallback to identity: %s", e)
        return lambda x: x


# Backward compatibility
unit_transfer_with_cache = unit_transfer_llm


# ======================================================
# Tools
# ======================================================

def clear_unit_cache() -> None:
    """Clear unified cache file + memory cache."""
    _INMEMO_CACHE.clear()
    if os.path.exists(UNIT_CACHE_PATH):
        os.remove(UNIT_CACHE_PATH)


def list_cached_conversions() -> list:
    """List all cache entries."""
    cache = _load_global_cache()
    result = []
    for key, item in cache.items():
        result.append({
            "from": item.get("project_unit"),
            "to": item.get("target_unit"),
            "mode": item.get("mode"),
            "function": item.get("transfer_func"),
        })
    return result
