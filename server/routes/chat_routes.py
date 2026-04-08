"""
Chat routes for CarbonPilot.
Handles chat interactions with the LLM.
"""

import logging
from typing import List, AsyncGenerator
import json
from collections import deque

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from configs.llm_wrapper import LLMWrapper
from ..routes.models import ChatMessage, ChatRequest
from server.langchain_tools import create_carbon_analysis_tools
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.tools import tool
from utils.internet_search import DDGSearchTool

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory storage for chat histories (in production, you might want to use Redis or a database)
chat_histories = {}

# Maximum number of messages to keep in history
MAX_HISTORY_LENGTH = 50
_search_engine = DDGSearchTool()
@tool
def internet_search(query: str) -> str:
    """Search internet for carbon prices, regulations, and external data."""
    return _search_engine.run(query)
class ChatMemory:
    """Manage chat history for each project"""
    
    def __init__(self, project_name: str, max_length: int = MAX_HISTORY_LENGTH):
        self.project_name = project_name
        self.max_length = max_length
        if project_name not in chat_histories:
            chat_histories[project_name] = deque(maxlen=max_length)
    
    def add_message(self, message: ChatMessage):
        """Add a message to the chat history"""
        chat_histories[self.project_name].append(message)
    
    def get_history(self) -> List[ChatMessage]:
        """Get the current chat history"""
        return list(chat_histories[self.project_name])
    
    def clear_history(self):
        """Clear the chat history"""
        chat_histories[self.project_name].clear()
    
    def get_formatted_history(self):
        """Get chat history formatted for Langchain"""
        history = []
        for msg in chat_histories[self.project_name]:
            if msg.role == "user":
                history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                history.append(AIMessage(content=msg.content))
        return history
    

async def generate_agent_response(project_name: str, messages: List[ChatMessage], config=None):
    try:
        latest_message = messages[-1] if messages else None
        if not latest_message or latest_message.role != "user":
            raise ValueError("Last message must be from user")

        # ===== Memory =====
        memory = ChatMemory(project_name)
        memory.add_message(latest_message)

        chat_history = memory.get_history()

        # ===== Tools =====
        tools = create_carbon_analysis_tools(project_name)

        # ===== System Prompt（⚠️必须改成字符串）=====
        system_prompt = """You are an expert in carbon emission analysis.

You can:
- Analyze project emissions
- Identify high-emission components
- Suggest reduction strategies
- Use tools when necessary
- Use internet search for real-time data

Be precise, data-driven, and actionable."""

        # ===== LLM =====
        llm_wrapper = LLMWrapper.get_streaming_instance()

        agent = create_agent(
            model=llm_wrapper.get_langchain_llm(),
            tools=tools,
            system_prompt=system_prompt
        )

        # ===== 构造 messages（替代 chat_history）=====
        lc_messages = []

        for msg in chat_history[:-1]:
            lc_messages.append({
                "role": "user" if msg.role == "user" else "assistant",
                "content": msg.content
            })

        lc_messages.append({
            "role": "user",
            "content": latest_message.content
        })

        # ===== Streaming =====
        full_response = ""

        async for event in agent.astream_events({"messages": lc_messages}):

            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]

                if hasattr(chunk, "content") and chunk.content:
                    text = str(chunk.content)
                    yield f"data: {text}\n\n"
                    full_response += text

            elif event["event"] == "on_tool_start":
                tool_name = event["name"]
                yield f"data: 🔍 Using tool: {tool_name}\n\n"

            elif event["event"] == "on_tool_end":
                yield f"data: ✅ Tool finished\n\n"

        # ===== 保存历史 =====
        if full_response:
            memory.add_message(ChatMessage(role="assistant", content=full_response))

    except Exception as e:
        logger.error(f"Agent chat request failed: {e}")
        yield f"data: Error: {str(e)}\n\n"
@router.post("/chat")
async def chat_with_llm(request: ChatRequest):
    """
    Send a message to the agent-enabled chat system and stream the response
    
    Args:
        request: Chat request containing messages and configuration
        
    Returns:
        Streaming response from the LLM agent
    """
    try:
        # Create a generator for streaming the response
        async def generate():
            async for chunk in generate_agent_response(
                request.project_name, 
                request.messages, 
                request.config
            ):
                yield chunk
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Chat request setup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat request failed: {str(e)}")

@router.delete("/chat/history/{project_name}")
async def clear_chat_history(project_name: str):
    """
    Clear chat history for a specific project
    
    Args:
        project_name: Name of the project whose chat history to clear
        
    Returns:
        Success confirmation
    """
    try:
        if project_name in chat_histories:
            chat_histories[project_name].clear()
        
        return {"message": f"Chat history cleared for project {project_name}"}
    except Exception as e:
        logger.error(f"Failed to clear chat history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear chat history: {str(e)}")


@router.get("/chat/history/{project_name}")
async def get_chat_history(project_name: str):
    """
    Get chat history for a specific project
    
    Args:
        project_name: Name of the project whose chat history to retrieve
        
    Returns:
        Chat history
    """
    try:
        memory = ChatMemory(project_name)
        history = memory.get_history()
        return {"project_name": project_name, "history": history}
    except Exception as e:
        logger.error(f"Failed to retrieve chat history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")