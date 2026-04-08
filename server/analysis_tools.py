"""
Carbon Emission Analysis Tools for Langchain

This module provides specialized tools for analyzing carbon emission calculation results
and interacting with the CarbonPilot system. These tools are designed to work with Langchain
to enable intelligent agents to query and analyze carbon emission data effectively.
"""

import json
import csv
import os
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import logging
from configs.llm_wrapper import LLMWrapper
from utils.internet_search import create_universal_internet_agent

logger = logging.getLogger(__name__)


class CarbonEmissionAnalysisTools:
    """
    A collection of tools for analyzing carbon emission data and project results.
    """

    def __init__(self, project_name: str, project_root: str = None):
        """
        Initialize the analysis tools with a project name.
        
        Args:
            project_name: Name of the project to analyze
            project_root: Root path of the project (defaults to current working directory)
        """
        self.project_name = project_name
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
        self.result_dir = self.project_root / "static" / "result" / project_name

    def get_project_summary(self) -> Dict[str, Any]:
        """
        Get overall project summary including total emissions.
        
        Returns:
            Dictionary containing project summary information
        """
        try:
            summary_path = self.result_dir / "summary_emission.json"
            if summary_path.exists():
                with open(summary_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {"error": "Summary data not found"}
        except Exception as e:
            logger.error(f"Error getting project summary: {e}")
            return {"error": f"Failed to get project summary: {str(e)}"}

    def get_top_emission_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get items with the highest carbon emissions.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of items sorted by emission (highest first)
        """
        try:
            csv_path = self.result_dir / "subitems.csv"
            if not csv_path.exists():
                return [{"error": "Detailed CSV data not found"}]
                
            items = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        emission = float(row.get("emission_tco2", 0))
                        items.append({
                            "name": row.get("sub_item_work_name", ""),
                            "emission": emission,
                            "unit": "tCO2",
                            "details": {
                                "material_emission": float(row.get("material_emission_tco2", 0)),
                                "labor_emission": float(row.get("labor_emission_tco2", 0)),
                                "machinery_emission": float(row.get("machinery_emission_tco2", 0)),
                                "transport_emission": float(row.get("transport_emission_tco2", 0)),
                            }
                        })
                    except ValueError:
                        continue
            
            # Sort by emission (descending) and limit results
            items.sort(key=lambda x: x["emission"], reverse=True)
            return items[:limit]
        except Exception as e:
            logger.error(f"Error getting top emission items: {e}")
            return [{"error": f"Failed to get top emission items: {str(e)}"}]

    def get_emissions_by_category(self) -> Dict[str, float]:
        """
        Get total emissions grouped by category (material, labor, machinery, transport).
        
        Returns:
            Dictionary with emission totals by category
        """
        try:
            csv_path = self.result_dir / "subitems.csv"
            if not csv_path.exists():
                return {"error": "Category data not found"}
                
            categories = {
                "material": 0.0,
                "labor": 0.0,
                "machinery": 0.0,
                "transport": 0.0
            }
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        categories["material"] += float(row.get("material_emission_tco2", 0))
                        categories["labor"] += float(row.get("labor_emission_tco2", 0))
                        categories["machinery"] += float(row.get("machinery_emission_tco2", 0))
                        categories["transport"] += float(row.get("transport_emission_tco2", 0))
                    except ValueError:
                        continue
            
            return categories
        except Exception as e:
            logger.error(f"Error getting emissions by category: {e}")
            return {"error": f"Failed to get emissions by category: {str(e)}"}

    def search_items_by_name(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for items by name or partial name match.
        
        Args:
            search_term: Term to search for in item names
            limit: Maximum number of items to return
            
        Returns:
            List of matching items
        """
        try:
            csv_path = self.result_dir / "subitems.csv"
            if not csv_path.exists():
                return [{"error": "Detailed CSV data not found"}]
                
            items = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("sub_item_work_name", "")
                    if search_term.lower() in name.lower():
                        try:
                            emission = float(row.get("emission_tco2", 0))
                            items.append({
                                "name": name,
                                "emission": emission,
                                "unit": "tCO2",
                                "details": {
                                    "material_emission": float(row.get("material_emission_tco2", 0)),
                                    "labor_emission": float(row.get("labor_emission_tco2", 0)),
                                    "machinery_emission": float(row.get("machinery_emission_tco2", 0)),
                                    "transport_emission": float(row.get("transport_emission_tco2", 0)),
                                    "quantity": row.get("used_quantity", ""),
                                    "unit": row.get("used_unit", ""),
                                }
                            })
                        except ValueError:
                            continue
            
            # Sort by emission (descending) and limit results
            items.sort(key=lambda x: x["emission"], reverse=True)
            return items[:limit]
        except Exception as e:
            logger.error(f"Error searching items by name: {e}")
            return [{"error": f"Failed to search items by name: {str(e)}"}]

    def compare_with_industry_benchmark(self, item_name: str) -> Dict[str, Any]:
        """
        Compare an item's emission with industry benchmarks (if available).
        
        Args:
            item_name: Name of the item to compare
            
        Returns:
            Comparison results with benchmarks
        """
        try:
            # This is a simplified implementation
            # In a real-world scenario, this would connect to a benchmark database
            return {
                "item_name": item_name,
                "status": "Comparison feature requires integration with industry benchmark database",
                "note": "This is a placeholder for future implementation"
            }
        except Exception as e:
            logger.error(f"Error comparing with industry benchmark: {e}")
            return {"error": f"Failed to compare with industry benchmark: {str(e)}"}
    def get_project_structure_overview(self) -> Dict[str, Any]:
            """
            Get an overview of the project structure.
            
            Returns:
                Dictionary containing project structure information
            """
            try:
                detailed_tree_path = self.result_dir / "detailed_tree.json"
                if not detailed_tree_path.exists():
                    return {"error": "Detailed tree data not found"}
                    
                with open(detailed_tree_path, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                    
                # Check if project_data is a dictionary with children
                if isinstance(project_data, dict) and "children" in project_data:
                    children = project_data["children"]
                    structure = {
                        "project_name": project_data.get("name", "Unknown Project"),
                        "total_items": len(children),
                        "items": []
                    }
                    
                    # Get first few items as samples
                    for i, item in enumerate(children[:5]):
                        if isinstance(item, dict):
                            structure["items"].append({
                                "name": item.get('name', f'Item {i}'),
                                "level": item.get('level', 'Unknown'),
                                "emission": item.get('properties', {}).get('emission_tco2', 'N/A')
                            })
                            
                    if len(children) > 5:
                        structure["more_items_count"] = len(children) - 5
                        
                    return structure
                else:
                    return {"error": "Unexpected data format"}
            except Exception as e:
                logger.error(f"Error getting project structure overview: {e}")
                return {"error": f"Failed to get project structure overview: {str(e)}"}
        
    def get_carbon_intensity(self) -> Dict[str, Any]:
        """
        Calculate carbon intensity (emissions per unit of measurement).
        This requires additional project metrics like area or value.
        
        Returns:
            Carbon intensity information
        """
        try:
            summary = self.get_project_summary()
            if "error" in summary:
                return summary
                
            # Placeholder for carbon intensity calculation
            # This would need additional project data like total area or construction value
            return {
                "status": "Carbon intensity calculation requires additional project metrics",
                "total_emission_tco2": summary.get("project_total_emission_tco2", "N/A"),
                "note": "Provide project area or value for intensity calculation"
            }
        except Exception as e:
            logger.error(f"Error calculating carbon intensity: {e}")
            return {"error": f"Failed to calculate carbon intensity: {str(e)}"}

    def suggest_reduction_opportunities(self) -> List[Dict[str, Any]]:
        """
        Suggest opportunities for reducing carbon emissions based on analysis.
        
        Returns:
            List of suggested reduction opportunities
        """
        try:
            # Get top emission items
            top_items = self.get_top_emission_items(5)
            if not top_items or "error" in top_items[0]:
                return top_items if top_items else [{"error": "Could not retrieve top items"}]
                
            # Get category breakdown
            categories = self.get_emissions_by_category()
            if "error" in categories:
                return [categories]
                
            suggestions = []
            
            # Suggestion based on top items
            for item in top_items[:3]:  # Focus on top 3 items
                if "error" not in item:
                    suggestions.append({
                        "type": "high_emission_item",
                        "item_name": item["name"],
                        "current_emission": item["emission"],
                        "suggestion": f"Consider alternative materials or methods for {item['name']} which contributes {item['emission']:.2f} tCO2 to total emissions"
                    })
            
            # Suggestion based on category breakdown
            highest_category = max(categories.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0)
            if isinstance(highest_category[1], (int, float)) and highest_category[1] > 0:
                suggestions.append({
                    "type": "category_focus",
                    "category": highest_category[0],
                    "emission": highest_category[1],
                    "suggestion": f"Focus on reducing {highest_category[0]} emissions, which account for {highest_category[1]:.2f} tCO2 of total emissions"
                })
                
            return suggestions
        except Exception as e:
            logger.error(f"Error suggesting reduction opportunities: {e}")
            return [{"error": f"Failed to suggest reduction opportunities: {str(e)}"}]


def create_analysis_toolkit(project_name: str) -> List[Dict[str, Any]]:
    """
    Create a toolkit of Langchain-compatible tools for carbon emission analysis.
    
    Args:
        project_name: Name of the project to analyze
        
    Returns:
        List of tool definitions compatible with Langchain
    """
    tools = []
    
    # Create an instance of our analysis tools
    analyzer = CarbonEmissionAnalysisTools(project_name)
    
    tools.append({
        "name": "get_project_summary",
        "description": "Get overall project summary including total emissions",
        "func": analyzer.get_project_summary,
        "args": {}
    })
    
    tools.append({
        "name": "get_top_emission_items",
        "description": "Get items with the highest carbon emissions",
        "func": analyzer.get_top_emission_items,
        "args": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to return (default: 10)",
                "default": 10
            }
        }
    })
    
    tools.append({
        "name": "get_emissions_by_category",
        "description": "Get total emissions grouped by category (material, labor, machinery, transport)",
        "func": analyzer.get_emissions_by_category,
        "args": {}
    })
    
    tools.append({
        "name": "search_items_by_name",
        "description": "Search for items by name or partial name match",
        "func": analyzer.search_items_by_name,
        "args": {
            "search_term": {
                "type": "string",
                "description": "Term to search for in item names"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of items to return (default: 10)",
                "default": 10
            }
        }
    })
    
    tools.append({
        "name": "get_project_structure_overview",
        "description": "Get an overview of the project structure",
        "func": analyzer.get_project_structure_overview,
        "args": {}
    })
    
    tools.append({
        "name": "suggest_reduction_opportunities",
        "description": "Suggest opportunities for reducing carbon emissions based on analysis",
        "func": analyzer.suggest_reduction_opportunities,
        "args": {}
    })
    
    return tools