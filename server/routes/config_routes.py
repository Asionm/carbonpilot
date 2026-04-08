"""
Configuration routes for CarbonPilot.
Handles system configuration management using .env file only.
"""

import json
import logging
import os
from typing import Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from dotenv import dotenv_values
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()  # Remove prefix, will be handled in main router

# Define the configuration model
class ConfigUpdate(BaseModel):
    neo4j_config: Dict[str, Any]
    llm_config: Dict[str, Any]
    agent_config: Dict[str, Any]

# Configuration file path
ENV_FILE = Path(".env")


def load_config_from_env(mask_api_key: bool = False):
    """Load configuration from .env file"""
    try:
        env_vars = dotenv_values(ENV_FILE)

        # Extract Neo4j config from env vars
        neo4j_config = {
            "uri": env_vars.get("NEO4J_URI", "bolt://localhost:7687"),
            "username": env_vars.get("NEO4J_USERNAME", "neo4j"),
            "password": env_vars.get("NEO4J_PASSWORD", ""),
            "database": env_vars.get("NEO4J_DATABASE", "neo4j")
        }

        # Extract LLM config
        api_key = env_vars.get("LLM_OPENAI_API_KEY", "")

        # 不再使用掩码，始终返回真实值
        llm_config = {
            "provider": env_vars.get("LLM_provider", "openai"),
            "model_name": env_vars.get("LLM_MODEL_NAME", "qwen3-next-80b-a3b-instruct"),
            "temperature": float(env_vars.get("LLM_TEMPERATURE", "0.7")),
            "max_tokens": int(env_vars.get("LLM_MAX_TOKENS", "32768")),
            "api_base": env_vars.get("LLM_OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "api_key": api_key
        }

        # Extract Agent config
        agent_config = {
            "information_enhancement": int(env_vars.get("INFORMATION_ENHANCEMENT", "0")),
            "wbs_correction": int(env_vars.get("WBS_CORRECTION", "1")),
            "agnetic_search": int(env_vars.get("AGNETIC_SEARCH", "1")),
            "factor_alignment_mode": int(env_vars.get("FACTOR_ALIGNMENT_MODE", "0")),
            "memory_information": int(env_vars.get("MEMORY_INFORAMTION", "1")),
            "memory_unit": int(env_vars.get("MEMORY_UNIT", "1"))
        }

        return {
            "neo4j_config": neo4j_config,
            "llm_config": llm_config,
            "agent_config": agent_config
        }

    except Exception as e:
        logger.error(f"Failed to load configuration from .env: {e}")
        return {
            "neo4j_config": {
                "uri": "bolt://localhost:7687",
                "username": "neo4j",
                "password": "",
                "database": "neo4j"
            },
            "llm_config": {
                "provider": "openai",
                "model_name": "qwen3-next-80b-a3b-instruct",
                "temperature": 0.7,
                "max_tokens": 32768,
                "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": ""
            },
            "agent_config": {
                "information_enhancement": 0,
                "wbs_correction": 1,
                "agnetic_search": 1,
                "factor_alignment_mode": 0,
                "memory_information": 1,
                "memory_unit": 1
            }
        }


def load_config(mask_api_key: bool = False):
    """Load configuration from .env file only"""
    return load_config_from_env(mask_api_key)


def save_config_to_env(config: Dict[str, Any]):
    """Save configuration to .env file"""
    try:
        env_lines = []
        if ENV_FILE.exists():
            with open(ENV_FILE, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()

        env_vars = {}

        # Handle Neo4j config
        for key, value in config["neo4j_config"].items():
            if key == "uri":
                env_key = "NEO4J_URI"
            elif key == "username":
                env_key = "NEO4J_USERNAME"
            elif key == "password":
                env_key = "NEO4J_PASSWORD"
            elif key == "database":
                env_key = "NEO4J_DATABASE"
            else:
                env_key = f"NEO4J_{key.upper()}"
            env_vars[env_key] = str(value)

        # Handle LLM config
        for key, value in config["llm_config"].items():
            if key == "provider":
                env_key = "LLM_provider"
            elif key == "api_base":
                env_key = "LLM_OPENAI_API_BASE"
            elif key == "api_key":
                env_key = "LLM_OPENAI_API_KEY"
            elif key == "model_name":
                env_key = "LLM_MODEL_NAME"
            elif key == "temperature":
                env_key = "LLM_TEMPERATURE"
            elif key == "max_tokens":
                env_key = "LLM_MAX_TOKENS"
            else:
                env_key = f"LLM_{key.upper()}"
            env_vars[env_key] = str(value)

        # Handle Agent config
        for key, value in config["agent_config"].items():
            if key == "information_enhancement":
                env_key = "INFORMATION_ENHANCEMENT"
            elif key == "wbs_correction":
                env_key = "WBS_CORRECTION"
            elif key == "agnetic_search":
                env_key = "AGNETIC_SEARCH"
            elif key == "factor_alignment_mode":
                env_key = "FACTOR_ALIGNMENT_MODE"
            elif key == "memory_information":
                env_key = "MEMORY_INFORAMTION"
            elif key == "memory_unit":
                env_key = "MEMORY_UNIT"
            else:
                env_key = key.upper()
            env_vars[env_key] = str(value)

        updated_lines = []
        existing_keys = set()

        for line in env_lines:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith('#'):
                updated_lines.append(line)
                continue

            if '=' in stripped_line:
                key = stripped_line.split('=')[0].strip()
                if key in env_vars:
                    updated_lines.append(f"{key}={env_vars[key]}\n")
                    existing_keys.add(key)
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)

        for key, value in env_vars.items():
            if key not in existing_keys:
                updated_lines.append(f"{key}={value}\n")

        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = ENV_FILE.with_suffix('.tmp')

        with open(temp_file, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)

        temp_file.replace(ENV_FILE)

        return True

    except Exception as e:
        logger.error(f"Failed to save configuration to .env file: {e}")
        return False


def save_config(config: Dict[str, Any]):
    """Save configuration to .env file only"""
    return save_config_to_env(config)


@router.get("/config/")
async def get_current_config():
    """
    Get current system configuration
    """
    try:
        # 不掩码敏感信息
        config = load_config(mask_api_key=False)
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to load configuration")


@router.post("/config/")
async def update_config(config_update: ConfigUpdate):
    """
    Update system configuration
    
    Args:
        config_update: Configuration object containing neo4j_config, llm_config and agent_config
        
    Returns:
        Updated configuration (without masking sensitive info)
    """
    try:
        # Save the configuration with real credentials
        success = save_config(config_update.dict())
        if success:
            # Reload environment variables to make them available to the current process
            import os
            from dotenv import load_dotenv
            # Reload the .env file
            load_dotenv(ENV_FILE, override=True)
            
            # Return the updated config (without masking sensitive info)
            # This allows the frontend to keep displaying the actual values the user entered
            return config_update.dict()
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to update configuration")
