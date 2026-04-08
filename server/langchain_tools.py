"""
Langchain Tools for CarbonPilot Carbon Emission Analysis

This module provides Langchain-compatible tools for analyzing carbon emission data.
These tools can be used with Langchain agents to enable intelligent querying of 
carbon emission results.
"""

from typing import Optional, Type, Any, Dict, List
from langchain.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import BaseModel, Field
from server.analysis_tools import CarbonEmissionAnalysisTools


class ProjectSummaryInput(BaseModel):
    """Input for getting project summary"""


class TopEmissionItemsInput(BaseModel):
    """Input for getting top emission items"""
    limit: int = Field(default=10, description="Maximum number of items to return")


class SearchItemsByNameInput(BaseModel):
    """Input for searching items by name"""
    search_term: str = Field(description="Term to search for in item names")
    limit: int = Field(default=10, description="Maximum number of items to return")


class GetProjectSummaryTool(BaseTool):
    """Tool for getting project summary"""
    
    name: str = "get_project_summary"
    description: str = "Get overall project summary including total emissions"
    args_schema: Type[BaseModel] = ProjectSummaryInput
    
    project_name: str
    
    def _run(
        self,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> Dict[str, Any]:
        """Get project summary"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.get_project_summary()


class GetTopEmissionItemsTool(BaseTool):
    """Tool for getting top emission items"""
    
    name: str = "get_top_emission_items"
    description: str = "Get items with the highest carbon emissions"
    args_schema: Type[BaseModel] = TopEmissionItemsInput
    
    project_name: str
    
    def _run(
        self,
        limit: int = 10,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> List[Dict[str, Any]]:
        """Get top emission items"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.get_top_emission_items(limit)


class GetEmissionsByCategoryTool(BaseTool):
    """Tool for getting emissions by category"""
    
    name: str = "get_emissions_by_category"
    description: str = "Get total emissions grouped by category (material, labor, machinery, transport)"
    args_schema: Type[BaseModel] = ProjectSummaryInput
    
    project_name: str
    
    def _run(
        self,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> Dict[str, float]:
        """Get emissions by category"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.get_emissions_by_category()


class SearchItemsByNameTool(BaseTool):
    """Tool for searching items by name"""
    
    name: str = "search_items_by_name"
    description: str = "Search for items by name or partial name match"
    args_schema: Type[BaseModel] = SearchItemsByNameInput
    
    project_name: str
    
    def _run(
        self,
        search_term: str,
        limit: int = 10,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> List[Dict[str, Any]]:
        """Search items by name"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.search_items_by_name(search_term, limit)


class GetProjectStructureOverviewTool(BaseTool):
    """Tool for getting project structure overview"""
    
    name: str = "get_project_structure_overview"
    description: str = "Get an overview of the project structure"
    args_schema: Type[BaseModel] = ProjectSummaryInput
    
    project_name: str
    
    def _run(
        self,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> Dict[str, Any]:
        """Get project structure overview"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.get_project_structure_overview()


class SuggestReductionOpportunitiesTool(BaseTool):
    """Tool for suggesting emission reduction opportunities"""
    
    name: str = "suggest_reduction_opportunities"
    description: str = "Suggest opportunities for reducing carbon emissions based on analysis"
    args_schema: Type[BaseModel] = ProjectSummaryInput
    
    project_name: str
    
    def _run(
        self,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> List[Dict[str, Any]]:
        """Suggest reduction opportunities"""
        analyzer = CarbonEmissionAnalysisTools(self.project_name)
        return analyzer.suggest_reduction_opportunities()


def create_carbon_analysis_tools(project_name: str) -> List[BaseTool]:
    """
    Create a list of Langchain tools for carbon emission analysis.
    
    Args:
        project_name: Name of the project to analyze
        
    Returns:
        List of Langchain tools
    """
    tools = [
        GetProjectSummaryTool(project_name=project_name),
        GetTopEmissionItemsTool(project_name=project_name),
        GetEmissionsByCategoryTool(project_name=project_name),
        SearchItemsByNameTool(project_name=project_name),
        GetProjectStructureOverviewTool(project_name=project_name),
        SuggestReductionOpportunitiesTool(project_name=project_name),
    ]
    
    return tools