# ======================================================
# LangChain Agent (v1) + JSON Post Processor
# ======================================================

from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional

from langchain.agents import create_agent
from langchain_core.tools import Tool

from configs.llm_wrapper import LLMWrapper

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None
    logging.warning("duckduckgo_search not installed.")

logger = logging.getLogger(__name__)


# ======================================================
# DuckDuckGo Tool
# ======================================================
class DDGSearchTool:
    """DuckDuckGo wrapper returning JSON"""

    def run(self, query: str) -> str:
        if DDGS is None:
            return json.dumps([{"error": "ddgs missing"}], ensure_ascii=False)

        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=8)

            return json.dumps([
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
                for r in results
            ], ensure_ascii=False)

        except Exception as e:
            return json.dumps([{"error": str(e)}], ensure_ascii=False)


# ======================================================
# Agent Factory
# ======================================================
def create_universal_internet_agent(system_prompt: Optional[str] = None):

    # 初始化 LLM
    llm_wrapper = LLMWrapper()
    llm = llm_wrapper.get_langchain_llm()

    # 工具
    tools = [
        Tool(
            name="ddg_search",
            description="Search the internet using DuckDuckGo.",
            func=DDGSearchTool().run,
        )
    ]

    # 默认 system prompt
    if not system_prompt:
        system_prompt = (
            "You are a professional research assistant.\n"
            "Use tools ONLY when necessary.\n"
            "Always produce structured outputs.\n"
        )

    # =========================
    # 创建新版 Agent（核心）
    # =========================
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )

    # ======================================================
    # Wrapper: 强制 JSON 输出
    # ======================================================
    def run_agent(task: str, output_format: str) -> Dict[str, Any]:

        # ---------- Step 1: Agent 推理 ----------
        result = agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{task}\n\n"
                        f"Your final answer MUST follow this JSON format:\n{output_format}"
                    )
                }
            ]
        })

        # 提取最终回答
        try:
            final_answer = result["messages"][-1].content
        except Exception:
            final_answer = str(result)

        # ---------- Step 2: JSON 修复 ----------
        fixer_llm = llm_wrapper.get_langchain_llm()

        fix_prompt = (
            "You MUST output a single valid JSON object.\n"
            "No explanation, no markdown.\n\n"
            f"Required JSON format:\n{output_format}\n\n"
            f"Model output:\n{final_answer}"
        )

        fixed = fixer_llm.invoke(fix_prompt)

        # ---------- Step 3: JSON 校验 ----------
        try:
            if isinstance(fixed, str):
                return json.loads(fixed)
            else:
                return json.loads(str(fixed))
        except Exception:
            return {
                "error": "Model failed to produce valid JSON",
                "required_format": output_format,
                "raw_model_output": final_answer,
                "raw_fix_attempt": str(fixed),
            }

    return run_agent