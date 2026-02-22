"""Tools module for Specta AI Mini-Agent architecture.

This module implements the Tool layer for the Mini-Agent architecture,
following MiniMax Mini-Agent design patterns.
"""

# New class-based Tools (A1-A5) following MiniMax design
from app.tools.a1_brand_competition import BrandCompetitionTool
from app.tools.a2_marketing_persona import MarketingPersonaTool
from app.tools.a3_question_simulation import QuestionSimulationTool
from app.tools.a4_fetch_agent import FetchAgentTool
from app.tools.a5_data_analytics import DataAnalyticsTool

__all__ = [
    # New class-based Tools (A1-A5)
    "BrandCompetitionTool",
    "MarketingPersonaTool",
    "QuestionSimulationTool",
    "FetchAgentTool",
    "DataAnalyticsTool",
]
