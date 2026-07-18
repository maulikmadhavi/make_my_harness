"""Web tools: search (Tavily or Brave, key from env) and generic HTTP requests."""

import json
import os

import requests

from make_harness.tools import tool

MAX_OUTPUT = 10_000


@tool
def web_search(query: str) -> str:
    """Search the web and return the top results (title, URL, snippet)."""
    tavily_key = os.getenv("TAVILY_API_KEY")
    brave_key = os.getenv("BRAVE_API_KEY")
    if tavily_key:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": query, "max_results": 5},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        lines = [f"- {x['title']}\n  {x['url']}\n  {x.get('content', '')[:300]}" for x in results]
        return "\n".join(lines) or "No results."
    if brave_key:
        r = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={"X-Subscription-Token": brave_key, "Accept": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("web", {}).get("results", [])
        lines = [f"- {x['title']}\n  {x['url']}\n  {x.get('description', '')[:300]}" for x in results]
        return "\n".join(lines) or "No results."
    return "Error: no search API key configured. The user must set TAVILY_API_KEY or BRAVE_API_KEY."


@tool
def http_request(method: str, url: str, headers_json: str = "", body_json: str = "") -> str:
    """Make an HTTP request to an API and return the status code and response body.

    headers_json and body_json are optional JSON object strings.
    """
    headers = json.loads(headers_json) if headers_json else {}
    body = json.loads(body_json) if body_json else None
    r = requests.request(method.upper(), url, headers=headers, json=body, timeout=30)
    text = r.text
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n[truncated {len(text) - MAX_OUTPUT} chars]"
    return f"status: {r.status_code}\n{text}"
