"""
Memory-based cross-project quota matching cache.

This module implements:
- Persistent global step counter
- Memory decay using forgetting curve
- Reinforcement when a memory item is reused
- Three memory states: strong / medium / weak
- LLM validation when memory confidence is medium
"""

import json
import os
import copy
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------------------------------
# Hyperparameters for memory mechanism
# -----------------------------------------------------
LAMBDA = 0.05              # Decay rate in forgetting curve
ALPHA = 0.7                # Reinforcement weight
STRONG_THRESHOLD = 0.6     # Above → strong memory
WEAK_THRESHOLD = 0.2       # Below → weak memory


# =====================================================
#  Load & Save Cache + Persistent Global Step
# =====================================================
def load_name_based_cache(
    path: str = "static/quota_cache/name_based_cache.json"
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load memory-aware quota cache."""
    try:
        if os.path.exists(path) and os.path.getsize(path) > 10:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cache = data.get("entries", {})
            meta = data.get("meta", {"global_step": 0})

            logger.info("[CACHE] Loaded %d items, global_step=%d", 
                        len(cache), meta["global_step"])
            return cache, meta

        return {}, {"global_step": 0}

    except Exception as e:
        logger.warning("[CACHE] Failed to load: %s", e)
        return {}, {"global_step": 0}


def save_name_based_cache(
    cache: Dict[str, Any],
    meta: Dict[str, Any],
    path: str = "static/quota_cache/name_based_cache.json"
):
    """Save cache with meta information."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            "meta": meta,
            "entries": cache
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("[CACHE] Saved %d items, global_step=%d", 
                    len(cache), meta["global_step"])

    except Exception as e:
        logger.warning("[CACHE] Failed to save: %s", e)

# -----------------------------------------------------
# Memory Strength Functions
# -----------------------------------------------------
def decay_memory(strength: float, t: int) -> float:
    """Apply forgetting curve: M(t)=M0 * exp(-λ t)."""
    return strength * math.exp(-LAMBDA * max(t, 0))


def reinforce_memory(strength: float) -> float:
    """Reinforcement rule after reuse."""
    return ALPHA * strength + (1 - ALPHA)


def get_memory_state(strength: float) -> str:
    """Map memory strength into discrete states."""
    if strength >= STRONG_THRESHOLD:
        return "strong"
    elif strength <= WEAK_THRESHOLD:
        return "weak"
    else:
        return "medium"



def get_cached_quota_result(
    cache: Dict[str, Any],
    meta: Dict[str, Any],
    name: str,
    project_info: str,
    llm_wrapper=None
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    Main memory-aware retrieval function.

    Behavior by memory state:
    - strong  → immediate reuse
    - medium  → verify with LLM (yes/no)
    - weak    → item forgotten (removed)
    """
    # Step increases globally
    meta["global_step"] += 1
    global_step = meta["global_step"]

    if name not in cache:
        return None

    entry = cache[name]
    mem = entry["memory"]

    # Compute time gap and apply decay
    t = global_step - mem["last_used_step"]
    strength = decay_memory(mem["strength"], t)
    state = get_memory_state(strength)

    logger.info("[MEMORY] '%s': strength=%.3f, state=%s, t=%d", 
                name, strength, state, t)

    # --------------------------
    # Case 1: Strong memory
    # --------------------------
    if state == "strong":
        logger.info(" → Strong memory: direct reuse.")

        # Reinforce
        mem["strength"] = reinforce_memory(strength)
        mem["last_used_step"] = global_step
        mem["use_count"] += 1

        entry["memory"] = mem
        return copy.deepcopy(entry["best_item"]), copy.deepcopy(entry["resource_items"])

    # --------------------------
    # Case 2: Weak memory
    # --------------------------
    if state == "weak":
        logger.info(" → Weak memory: removing cache entry.")
        del cache[name]
        return None

    # --------------------------
    # Case 3: Medium memory → LLM validation
    # --------------------------
    if llm_wrapper is None:
        logger.warning("Medium memory but no LLM available → fallback reuse.")
        return copy.deepcopy(entry["best_item"]), copy.deepcopy(entry["resource_items"])

    validation_prompt = f"""
The following quota was previously matched:
{entry['best_item']}

Project info: {project_info}

Check if this cached quota is STILL appropriate.
Answer strictly with: "yes" or "no".
"""

    resp = llm_wrapper.generate_response(validation_prompt).strip().lower()
    logger.info("LLM validation → %s", resp)

    if resp.startswith("yes"):
        logger.info(" → Medium memory validated by LLM: reuse.")

        # Reinforce memory
        mem["strength"] = reinforce_memory(strength)
        mem["last_used_step"] = global_step
        mem["use_count"] += 1
        entry["memory"] = mem

        return copy.deepcopy(entry["best_item"]), copy.deepcopy(entry["resource_items"])

    else:
        logger.info(" → Medium memory rejected: removing entry.")
        del cache[name]
        return None

def save_quota_result_to_cache(
    cache: Dict[str, Any],
    meta: Dict[str, Any],
    name: str,
    best_item: Dict[str, Any],
    resource_items: List[Dict[str, Any]]
):
    """Save a new cache entry with initialized memory strength."""
    global_step = meta["global_step"]

    cache[name] = {
        "best_item": copy.deepcopy(best_item),
        "resource_items": copy.deepcopy(resource_items),
        "memory": {
            "strength": 1.0,
            "use_count": 1,
            "last_used_step": global_step,
            "state": "strong"
        }
    }

    logger.info("[CACHE] Added new entry: %s", name)
