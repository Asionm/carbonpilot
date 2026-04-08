"""
Data models for CarbonPilot API.
Contains Pydantic models for request/response validation.
"""

from typing import Optional, List
from pydantic import BaseModel


class LLMConfig(BaseModel):
    """
    Configuration for Large Language Model
    """
    provider: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None


class AgentConfig(BaseModel):
    """
    Configuration for agent behaviors
    """
    agent_query: Optional[bool] = None
    think_mode: Optional[str] = None
    
    # Step 1 configuration
    enhance_s1: Optional[bool] = None
    enhance_s2: Optional[bool] = None
    
    # Step 2 configuration
    member_add: Optional[bool] = None
    use_reranker: Optional[bool] = None
    use_memory: Optional[bool] = None
    
    # Transport step configuration
    transport_use_memory: Optional[bool] = None
    
    # Step 4 configuration
    alignment_mode: Optional[str] = None
    emission_use_memory: Optional[bool] = None


class CalculationConfig(BaseModel):
    """
    Configuration for carbon emission calculation
    """
    llm_config: Optional[LLMConfig] = None
    agent_config: Optional[AgentConfig] = None


class ChatMessage(BaseModel):
    """
    Model for chat messages
    """
    role: str
    content: str


class ChatRequest(BaseModel):
    """
    Request model for chat endpoint
    """
    project_name: str
    messages: List[ChatMessage]
    config: Optional[LLMConfig] = None