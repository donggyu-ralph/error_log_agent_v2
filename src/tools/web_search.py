"""Tavily web search tool."""
from langchain_community.tools.tavily_search import TavilySearchResults

from src.config.settings import get_settings


def get_web_search_tool():
    """Get Tavily search tool."""
    settings = get_settings()
    if not settings.web_search.enabled:
        return None
    return TavilySearchResults(max_results=settings.web_search.max_results)
