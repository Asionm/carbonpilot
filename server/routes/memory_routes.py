"""
Memory/cache routes for CarbonPilot.
Handles memory/cache management operations.
"""

import json
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

# Define cache directories - focusing on quota and unit caches as primary usage
CACHE_DIRS = {
    "quota": Path("static/quota_cache"),
    "unit": Path("static/unit_cache")
}


@router.get("/memory")
async def get_memory_status():
    """
    Get status of all memory caches
    
    Returns:
        Status information for quota and unit cache directories
    """
    status = {}
    for cache_name, cache_path in CACHE_DIRS.items():
        if cache_path.exists():
            file_count = len(list(cache_path.iterdir()))
            status[cache_name] = {
                "path": str(cache_path),
                "file_count": file_count
            }
        else:
            status[cache_name] = {
                "path": str(cache_path),
                "file_count": 0,
                "exists": False
            }
    
    return status


@router.get("/memory/{memory_type}/{filename}")
async def get_memory_content(memory_type: str, filename: str):
    """
    Get content of a specific memory file
    
    Args:
        memory_type: Type of memory/cache (quota, unit)
        filename: Name of the file to retrieve
        
    Returns:
        Content of the specified memory file
    """
    if memory_type not in CACHE_DIRS:
        raise HTTPException(status_code=404, detail=f"Memory type '{memory_type}' not supported. Supported types: quota, unit")
    
    cache_path = CACHE_DIRS[memory_type]
    file_path = cache_path / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in '{memory_type}' memory")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        return content
    except json.JSONDecodeError:
        # If not valid JSON, return as plain text
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        logger.error(f"Failed to read memory file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read memory file: {str(e)}")


@router.put("/memory/{memory_type}/{filename}")
async def update_memory_content(memory_type: str, filename: str, content: dict):
    """
    Update content of a specific memory file
    
    Args:
        memory_type: Type of memory/cache (quota, unit)
        filename: Name of the file to update
        content: New content to write to the file
        
    Returns:
        Success message
    """
    if memory_type not in CACHE_DIRS:
        raise HTTPException(status_code=404, detail=f"Memory type '{memory_type}' not supported. Supported types: quota, unit")
    
    cache_path = CACHE_DIRS[memory_type]
    file_path = cache_path / filename
    
    # Create directory if it doesn't exist
    cache_path.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        return {"message": f"Successfully updated {filename}"}
    except Exception as e:
        logger.error(f"Failed to update memory file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update memory file: {str(e)}")


@router.delete("/memory/{memory_type}")
async def clear_memory_type(memory_type: str):
    """
    Clear all files in a specific memory type
    
    Args:
        memory_type: Type of memory/cache to clear (quota, unit)
        
    Returns:
        Success message
    """
    if memory_type not in CACHE_DIRS:
        raise HTTPException(status_code=404, detail=f"Memory type '{memory_type}' not supported. Supported types: quota, unit")
    
    cache_path = CACHE_DIRS[memory_type]
    
    if not cache_path.exists():
        return {"message": f"Memory type '{memory_type}' is already empty"}
    
    try:
        for file_path in cache_path.iterdir():
            if file_path.is_file():
                file_path.unlink()
        return {"message": f"Successfully cleared '{memory_type}' memory"}
    except Exception as e:
        logger.error(f"Failed to clear memory type {memory_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear memory: {str(e)}")