"""
General Utility Functions

This module provides various utility functions used throughout the CarbonPilot project.
"""

import logging
import re
from typing import Any, Dict, Generator, List, Optional, Union, Iterator, Tuple
import csv
import json

from litellm import BaseModel

from schemes.project_info import ConstructionProject, IndividualProject, SpecialtySubdivision, SubDivisionalWork, SubItemWork, UnitProject, WBSNode, WBSRoot

logger = logging.getLogger(__name__)


def _safe_get(d: Dict[str, Any], *keys: str, default=None):
    """
    Safely get a value from a nested dictionary.
    
    Args:
        dictionary: The dictionary to get the value from
        keys: The keys to traverse
        default: The default value to return if the key is not found
        
    Returns:
        The value or default
    """
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default if k == keys[-1] else {})
    return cur


def _coerce_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def _to_tons(kg: float) -> float:
    return float(kg) / 1000.0


def _normalize_co2_unit(factor_unit: Optional[str]) -> Tuple[float, str, Optional[str]]:
    """
      "kgCO2/kg"  -> (1.0, "kgCO2", "kg")
      "tCO2/m3"   -> (1000.0, "kgCO2", "m3")
      "kgCO2"     -> (1.0, "kgCO2", None)
      None/空     -> (1.0, "kgCO2", None)
    """
    if not factor_unit:
        return 1.0, "kgCO2", None

    unit = str(factor_unit).replace(" ", "").lower()

    parts = unit.split("/")
    numerator = parts[0]
    denom = parts[1] if len(parts) > 1 else None

    if "tco2" in numerator:
        mult = 1000.0
    elif "kgco2" in numerator:
        mult = 1.0
    elif "gco2" in numerator:
        mult = 0.001
    else:
        mult = 1.0

    return mult, "kgCO2", denom


def _iter_sub_item_works(project: Dict[str, Any]) -> Generator[
    Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]],
    None,
    None
]:
    
    for indiviual_project in project.get("children", []):
        unit_projects = indiviual_project.get("children", [])
        for unit_project in unit_projects:
            sub_divisional_works = unit_project.get("children", [])
            for sub_divisional_work in sub_divisional_works:
                specialty_subdivisions = sub_divisional_work.get("children", [])
                for specialty_subdivision in specialty_subdivisions:
                    sub_item_works = specialty_subdivision.get("children", [])
                    for sub_item_work in sub_item_works:
                        if sub_item_work.get("level") == "sub_item_work":
                            yield (
                                indiviual_project,
                                unit_project,
                                sub_divisional_work,
                                specialty_subdivision,
                                sub_item_work,
                                project,
                            )


def _extract_resource_base_value(res: Dict[str, Any]) -> Tuple[float, str]:
    """
    Extract the base value and unit from a resource.
    
    Args:
        resource: The resource dictionary
        
    Returns:
        Tuple of (value, unit)
    """
    if isinstance(res, dict):
        # 常见两种结构：res["value"] 或 res["properties"]["value"]
        if isinstance(res.get("value"), (int, float)):
            return float(res["value"])
        props = res.get("properties") or {}
        if isinstance(props.get("value"), (int, float)):
            return float(props["value"])
        # 再尝试字符串转数值
        raw = res.get("value")
        if isinstance(raw, str):
            try:
                return float(raw)
            except Exception:
                pass
    return 0.0


def extract_csv_list(input_data: str, encoding: str = 'utf-8') -> List[Dict[str, Any]]:
    """
    Extract data from a CSV file as a list of dictionaries or parse text as a list.
    
    Args:
        input_data: Path to the CSV file or text string to parse
        encoding: Encoding of the CSV file (only used when input_data is a file path)
        
    Returns:
        List of dictionaries representing the CSV data or list of parsed items
    """
    # Check if input_data looks like JSON data (starts with [ or {)
    text = (input_data or "").strip()
    if text.startswith("[") or text.startswith("{"):
        # This looks like JSON/text data, not a file path
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
            if isinstance(data, dict) and isinstance(data.get("order"), list):
                return [str(x).strip() for x in data["order"] if str(x).strip()]
        except Exception:
            pass
        return [x.strip() for x in re.split(r"[,\n]", text) if x.strip()]
    else:
        # This looks like a file path
        data = []
        try:
            with open(input_data, 'r', encoding=encoding) as csvfile:
                reader = csv.DictReader(csvfile)
                data = list(reader)
        except Exception as e:
            logger.error(f"Error reading CSV file {input_data}: {e}")
        
        return data


def check_fix_wbs(wbs_root: Union[WBSRoot, dict]) -> WBSRoot:
    """
    Final stable WBS repair function.
    Guarantees:
    - No dict ever reaches _fix without being converted to model.
    - No invalid structure reaches Pydantic validation.
    - No direct sub_item_work under sub_divisional_work.
    - All missing hierarchy levels inserted.
    """

    LEVELS = [
        "construction_project",
        "individual_project",
        "unit_project",
        "sub_divisional_work",
        "specialty_subdivision",
        "sub_item_work",
    ]

    CLASS_OF = {
        "construction_project": ConstructionProject,
        "individual_project": IndividualProject,
        "unit_project": UnitProject,
        "sub_divisional_work": SubDivisionalWork,
        "specialty_subdivision": SpecialtySubdivision,
        "sub_item_work": SubItemWork,
    }

    # ------------------ DEFAULT NODE ------------------
    def _default_node(level: str) -> dict:
        if level == "sub_item_work":
            return {
                "level": level,
                "name": "unnamed_item",
                "description": "",
                "unit": "item",
                "quantity": 1,
            }
        return {
            "level": level,
            "name": "unnamed_level",
            "description": "",
            "children": [],
        }

    # ------------------ STEP 1: PRE FIX (DICT ONLY) ------------------
    def _pre_fix(node: dict) -> dict:
        level = node.get("level")
        if not isinstance(level, str):
            return node

        raw_children = node.get("children", [])
        if not isinstance(raw_children, list):
            raw_children = []
        node["children"] = raw_children

        # Fix: sub_divisional_work cannot contain sub_item_work directly
        if level == "sub_divisional_work":
            if any(c.get("level") == "sub_item_work" for c in raw_children):
                node["children"] = [{
                    "level": "specialty_subdivision",
                    "name": "default",
                    "description": "auto-generated",
                    "children": raw_children,
                }]

        # Recurse
        node["children"] = [
            _pre_fix(c) if isinstance(c, dict) else c
            for c in node["children"]
        ]
        return node

    # ------------------ STEP 2: ENSURE MODEL ------------------
    def _ensure_model(node: Union[dict, BaseModel]) -> BaseModel:
        if isinstance(node, BaseModel):
            return node

        # Ensure all children converted
        children = []
        for c in node.get("children", []):
            processed_child = _ensure_model(c)
            # If it's a sub_item_work and processing failed due to validation errors, skip it
            if processed_child is not None:
                children.append(processed_child)

        cls = CLASS_OF[node["level"]]

        if node["level"] == "sub_item_work":
            # Handle potential validation errors for SubItemWork
            # Create a copy of the node to modify
            sub_item_node = node.copy()
            
            # Check if quantity is an empty string or invalid and handle it
            quantity_val = sub_item_node.get("quantity", 0)
            if quantity_val == "" or quantity_val is None:
                # Log the issue and set a default value
                logger.warning(f"Invalid quantity value '{quantity_val}', setting default value 0 for sub_item_work: {sub_item_node.get('name', 'unnamed')}")
                sub_item_node["quantity"] = 0
            else:
                # Try to convert quantity to float, if it fails use default
                try:
                    sub_item_node["quantity"] = float(quantity_val)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid quantity value '{quantity_val}', setting default value 0 for sub_item_work: {sub_item_node.get('name', 'unnamed')}")
                    sub_item_node["quantity"] = 0
            
            # Handle unit field if it's empty
            unit_val = sub_item_node.get("unit", "item")
            if unit_val == "":
                logger.warning(f"Empty unit value, setting default value 'item' for sub_item_work: {sub_item_node.get('name', 'unnamed')}")
                sub_item_node["unit"] = "item"

            return cls(**sub_item_node)

        return cls(
            children=children,
            **{k: v for k, v in node.items() if k != "children"}
        )

    # ------------------ STEP 3: INSERT MISSING LEVELS ------------------
    def _insert_missing(parent: BaseModel, child: BaseModel) -> BaseModel:
        parent_idx = LEVELS.index(parent.level)
        child_idx = LEVELS.index(child.level)

        if child_idx == parent_idx + 1:
            return child

        wrapped = child
        for lv in reversed(LEVELS[parent_idx + 1:child_idx]):
            new_node = _ensure_model(_default_node(lv))
            new_node.children = [wrapped]
            wrapped = new_node

        return wrapped

    # ------------------ STEP 4: FIX TREE (MODEL ONLY) ------------------
    def _fix(node: Union[dict, BaseModel]) -> BaseModel:

        # GUARANTEE model
        if isinstance(node, dict):
            node = _ensure_model(node)

        # Leaf node
        if node.level == "sub_item_work":
            return node

        fixed_children = []
        for c in node.children:

            # Guarantee child is model
            if isinstance(c, dict):
                c = _ensure_model(c)

            fixed = _fix(c)
            fixed = _insert_missing(node, fixed)
            fixed_children.append(fixed)

        node.children = fixed_children
        return node

    # ------------------ EXECUTION PIPELINE ------------------
    if isinstance(wbs_root, dict):
        wbs_root = _pre_fix(wbs_root)

    model_root = _ensure_model(wbs_root)
    model_root = _fix(model_root)

    return WBSRoot.model_validate(model_root.model_dump())
