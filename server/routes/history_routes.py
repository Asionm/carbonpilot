"""
History routes for CarbonPilot.
Handles retrieving historical project data.
"""

import json
import logging
from pathlib import Path
import os

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# Define the result directory
RESULT_DIR = Path(__file__).parent.parent.parent / "static" / "result"

router = APIRouter()


@router.get("/history")
async def get_history_projects():
    """
    Get list of all historical projects with their details
    
    Returns:
        List of project details including name, total emission and calculation date
    """
    logger.info(RESULT_DIR)
    if not RESULT_DIR.exists():
        return []
    
    projects = []
    for item in RESULT_DIR.iterdir():
        if item.is_dir():
            # Try to get project details from summary_emission.json
            summary_file = item / "summary_emission.json"
            calculation_date = os.path.getmtime(item) if os.path.exists(item) else os.path.getctime(item)
            
            total_emission = "Unknown"
            calculation_time = "Unknown"
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_data = json.load(f)
                        if isinstance(summary_data, dict) and "project_total_emission_tco2" in summary_data:
                            total_emission = summary_data["project_total_emission_tco2"]
                        
                        # 获取计算时间
                        if isinstance(summary_data, dict) and "calculation_time" in summary_data:
                            calculation_time = summary_data["calculation_time"]
                except Exception as e:
                    logger.warning(f"Failed to load summary_emission.json for {item.name}: {e}")
            
            projects.append({
                "project_name": item.name,
                "total_emission": total_emission,
                "calculation_date": calculation_date,
                "calculation_time": calculation_time
            })
    
    return projects


@router.get("/history/{project_name}")
async def get_history_project_detail(project_name: str):
    """
    Get detailed information of a specific historical project
    
    Args:
        project_name: Name of the project
        
    Returns:
        Detailed information including tree data, emissions summary, etc.
    """
    project_dir = RESULT_DIR / project_name
    
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    result = {}
    
    # Try to load detailed tree data
    detailed_tree_file = project_dir / "detailed_tree.json"
    if detailed_tree_file.exists():
        try:
            with open(detailed_tree_file, "r", encoding="utf-8") as f:
                result["detailed_tree"] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load detailed_tree.json: {e}")
    
    # Try to load summary emission data
    summary_file = project_dir / "summary_emission.json"
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                result["summary_emission"] = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load summary_emission.json: {e}")
    
    # Add project_name to the result for frontend display
    result["project_name"] = project_name
    
    # Try to load subitems CSV data
    subitems_file = project_dir / "subitems.csv"
    if subitems_file.exists():
        try:
            with open(subitems_file, "r", encoding="utf-8") as f:
                result["subitems_csv"] = f.read()
        except Exception as e:
            logger.warning(f"Failed to load subitems.csv: {e}")
    
    # Process data for visualizations if detailed_tree exists
    if "detailed_tree" in result:
        # Add processed data for various visualizations
        result["visualization_data"] = {
            "project_emissions": _process_project_emissions(result["detailed_tree"]),
            "phase_emissions": _process_phase_emissions(result["detailed_tree"]),
            "resource_category_emissions": _process_resource_category_emissions(result["detailed_tree"]),
            "material_emissions": _process_material_emissions(result["detailed_tree"])
        }
    
    # Ensure total_emission is present in result
    if "summary_emission" in result and "project_total_emission_tco2" in result["summary_emission"]:
        result["total_emission"] = result["summary_emission"]["project_total_emission_tco2"]
    elif "summary_emission" in result:
        # Handle case where summary_emission exists but doesn't have project_total_emission_tco2
        result["total_emission"] = 0
    else:
        # Handle case where summary_emission doesn't exist
        result["total_emission"] = 0
    
    if not result:
        raise HTTPException(status_code=404, detail="No data found for project")
        
    return result


@router.delete("/history/{project_name}")
async def delete_history_project(project_name: str):
    """
    Delete a historical project by removing its entire folder
    
    Args:
        project_name: Name of the project to delete

    Returns:
        Success message
    """
    project_dir = RESULT_DIR / project_name

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        # Remove the entire directory recursively
        import shutil
        shutil.rmtree(project_dir)

        # Also remove extraction cache files
        from pathlib import Path
        extraction_cache_dir = Path(__file__).parent.parent.parent / "static" / "extraction_cache"
        enhanced_file = extraction_cache_dir / f"{project_name}_wbs.json"
        raw_file = extraction_cache_dir / f"{project_name}_wbs_raw.json"
        
        if enhanced_file.exists():
            enhanced_file.unlink()
        
        if raw_file.exists():
            raw_file.unlink()

        return {"message": f"Project '{project_name}' deleted successfully"}
    
    except Exception as e:
        logger.error(f"Failed to delete project '{project_name}': {e}")
        raise HTTPException(status_code=500, detail="Failed to delete project")


def _process_project_emissions(tree_data):
    """
    Process data for project-level emissions visualization
    
    Args:
        tree_data: The detailed tree data
        
    Returns:
        List of projects with their emissions
    """
    projects = []
    
    def traverse_nodes(node, parent_name=""):
        if node.get("level") == "individual_project":
            project_name = node.get("name", "Unknown Project")
            emission = 0
            
            # Get emission from properties if available
            if "properties" in node and "emission_tco2" in node["properties"]:
                emission = node["properties"]["emission_tco2"]
            # Or sum up children emissions
            elif "children" in node:
                emission = _sum_children_emissions(node["children"])
                
            projects.append({
                "name": project_name,
                "emission": emission
            })
        elif "children" in node:
            for child in node["children"]:
                traverse_nodes(child, node.get("name", ""))
    
    traverse_nodes(tree_data)
    return projects


def _sum_children_emissions(children):
    """
    Sum up emissions from children nodes
    
    Args:
        children: List of child nodes
        
    Returns:
        Total emission value
    """
    total = 0
    for child in children:
        if "properties" in child and "emission_tco2" in child["properties"]:
            total += child["properties"]["emission_tco2"]
        elif "children" in child:
            total += _sum_children_emissions(child["children"])
    return total


def _process_phase_emissions(tree_data):
    """
    Process data for phase-level emissions visualization
    
    Args:
        tree_data: The detailed tree data
        
    Returns:
        List of construction phases with their emissions
    """
    phases = {}
    
    def traverse_nodes(node):
        if node.get("level") == "sub_divisional_work":
            phase_name = node.get("name", "Unknown Phase")
            emission = 0
            
            if "properties" in node and "emission_tco2" in node["properties"]:
                emission = node["properties"]["emission_tco2"]
            elif "children" in node:
                emission = _sum_children_emissions(node["children"])
                
            if phase_name in phases:
                phases[phase_name] += emission
            else:
                phases[phase_name] = emission
                
        elif "children" in node:
            for child in node["children"]:
                traverse_nodes(child)
    
    traverse_nodes(tree_data)
    
    # Convert to list format
    result = [{"name": name, "emission": emission} for name, emission in phases.items()]
    return result


def _process_resource_category_emissions(tree_data):
    """
    Process data for resource category emissions visualization
    
    Args:
        tree_data: The detailed tree data
        
    Returns:
        List of resource categories with their emissions
    """
    categories = {}
    
    def traverse_nodes(node):
        if node.get("level") == "sub_item_work" and "resource_items" in node:
            for resource in node["resource_items"]:
                category = resource.get("category", "Unknown")
                emission = resource.get("emission", 0) / 1000  # Convert kgCO2 to tCO2
                
                if category in categories:
                    categories[category] += emission
                else:
                    categories[category] = emission
                    
        elif "children" in node:
            for child in node["children"]:
                traverse_nodes(child)
    
    traverse_nodes(tree_data)
    
    # Convert to list format
    result = [{"category": category, "emission": emission, "count": 0} 
              for category, emission in categories.items()]
    
    # Count resources in each category
    category_counts = {}
    def count_resources(node):
        if node.get("level") == "sub_item_work" and "resource_items" in node:
            for resource in node["resource_items"]:
                category = resource.get("category", "Unknown")
                if category in category_counts:
                    category_counts[category] += 1
                else:
                    category_counts[category] = 1
        elif "children" in node:
            for child in node["children"]:
                count_resources(child)
    
    count_resources(tree_data)
    
    # Add counts to result
    for item in result:
        item["count"] = category_counts.get(item["category"], 0)
    
    return result


def _process_material_emissions(tree_data):
    """
    Process data for material emissions visualization
    
    Args:
        tree_data: The detailed tree data
        
    Returns:
        List of materials with their emissions
    """
    materials = {}
    
    def traverse_nodes(node):
        if node.get("level") == "sub_item_work" and "resource_items" in node:
            for resource in node["resource_items"]:
                # Only consider Material category for this chart
                if resource.get("category") == "Material":
                    material_name = resource.get("resource_name", "Unknown Material")
                    emission = resource.get("emission", 0) / 1000  # Convert kgCO2 to tCO2
                    
                    if material_name in materials:
                        materials[material_name] += emission
                    else:
                        materials[material_name] = emission
                        
        elif "children" in node:
            for child in node["children"]:
                traverse_nodes(child)
    
    traverse_nodes(tree_data)
    
    # Convert to list format and sort by emission
    result = [{"name": name, "emission": emission, "category": "Material"} 
              for name, emission in materials.items()]
    
    # Sort by emission (descending)
    result.sort(key=lambda x: x["emission"], reverse=True)
    
    # Return top 10 materials
    return result[:10]