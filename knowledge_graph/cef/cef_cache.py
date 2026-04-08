"""
CEF Cache Processing Module
Used to cache LLM reranking results to reduce redundant computations
"""

import json
import os
import copy
import logging
from typing import Dict, Any, List, Optional

# ------------- Logging Configuration -------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def load_cef_cache(cache_file_path: str = "static/cef_cache/rerank_cache.json") -> Dict[str, str]:
    """
    Load CEF reranking cache from specified path
    
    Args:
        cache_file_path: Cache file path, defaults to static/cef_cache/rerank_cache.json
        
    Returns:
        Cache dictionary, key is cache key, value is best factor ID
    """
    try:
        if os.path.exists(cache_file_path) and os.path.getsize(cache_file_path) > 0:
            with open(cache_file_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            
            logger.info("Successfully loaded CEF reranking cache with %d items", len(cache_data))
            return cache_data
        else:
            logger.info("CEF reranking cache file does not exist or is empty")
            return {}
    except Exception as e:
        logger.warning("Failed to load CEF reranking cache: %s", e)
        return {}


def save_cef_cache(cef_cache: Dict[str, str], 
                   cache_file_path: str = "static/cef_cache/rerank_cache.json") -> None:
    """
    Save CEF reranking cache to specified path
    
    Args:
        cef_cache: Cache dictionary
        cache_file_path: Cache file save path, defaults to static/cef_cache/rerank_cache.json
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        
        # Save cache to file
        with open(cache_file_path, "w", encoding="utf-8") as f:
            json.dump(cef_cache, f, ensure_ascii=False, indent=2)
        
        logger.info("CEF reranking cache saved to: %s", cache_file_path)
    except Exception as e:
        logger.warning("Failed to save CEF reranking cache: %s", e)


def get_cached_cef_result(cef_cache: Dict[str, str], 
                          cache_key: str) -> Optional[str]:
    """
    Get CEF reranking result for specified key from cache
    
    Args:
        cef_cache: CEF cache dictionary
        cache_key: Cache key (generated based on project info and resource item)
        
    Returns:
        Best factor ID, returns None if not found
    """
    if cache_key in cef_cache:
        logger.info("Using cached CEF reranking result: %s", cache_key)
        return cef_cache[cache_key]
    return None


def save_cef_result_to_cache(cef_cache: Dict[str, str], 
                             cache_key: str, 
                             best_factor_id: str) -> None:
    """
    Save CEF reranking result to cache
    
    Args:
        cef_cache: CEF cache dictionary
        cache_key: Cache key
        best_factor_id: Best factor ID
    """
    cef_cache[cache_key] = best_factor_id
    logger.info("CEF reranking result cached: %s", cache_key)