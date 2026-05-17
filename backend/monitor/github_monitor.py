"""
GitHub Issues & Discussions lead monitor.
Uses the GitHub REST API search endpoint.
Unauthenticated: 10 req/min. With GITHUB_TOKEN: 30 req/min.
Great signal for dev-tool companies — people open issues asking "does X support Y?",
"looking for alternative to Z", "need help integrating with...".
"""
import logging

import httpx

from backend.database import settings

log = logging.getLogger(__name__)

_BASE = "https://api.github.com"


def _auth_headers() -> dict:
    token = getattr(settings, "GITHUB_TOKEN", "")
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MarketingMonitor/1.0",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _build_post(item: dict, kind: str = "issue") -> dict:
    item_id = item.get("id", "")
    title = item.get("title", "")
    body = (item.get("body") or "")[:1500]
    content = f"{title}\n\n{body}".strip() if body else title
    user = item.get("user", {}) or {}
    author = user.get("login") or ""
    return {
        "external_id": f"gh-{kind}-{item_id}",
        "content": content,
        "source_url": item.get("html_url") or None,
        "author_name": None,
        "author_username": author or None,
        "author_url": f"https://github.com/{author}" if author else None,
    }


def search_issues(query: str, limit: int = 20) -> list[dict]:
    """Search GitHub issues matching a query. Returns open issues sorted by creation date."""
    try:
        resp = httpx.get(
            f"{_BASE}/search/issues",
            params={
                "q": f"{query} is:issue is:open",
                "sort": "created",
                "order": "desc",
                "per_page": min(limit, 50),
            },
            headers=_auth_headers(),
            timeout=15,
        )
        if resp.status_code == 403:
            log.warning("GitHub API rate limited — add GITHUB_TOKEN to increase limits")
            return []
        resp.raise_for_status()
        posts = [_build_post(item, "issue") for item in resp.json().get("items", [])]
        log.info("GitHub issue search '%s': %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.exception("GitHub issue search failed for '%s'", query[:60])
        return []


def search_discussions(query: str, limit: int = 20) -> list[dict]:
    """Search GitHub Discussions via GraphQL API."""
    token = getattr(settings, "GITHUB_TOKEN", "")
    if not token:
        return []  # GraphQL requires auth
    graphql_query = """
    query($q: String!, $limit: Int!) {
      search(query: $q, type: DISCUSSION, first: $limit) {
        nodes {
          ... on Discussion {
            id
            title
            body
            url
            author { login }
          }
        }
      }
    }"""
    try:
        resp = httpx.post(
            "https://api.github.com/graphql",
            json={"query": graphql_query, "variables": {"q": query, "limit": limit}},
            headers={**_auth_headers(), "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        nodes = resp.json().get("data", {}).get("search", {}).get("nodes", [])
        posts = []
        for node in nodes:
            if not node:
                continue
            node_id = node.get("id", "")
            title = node.get("title", "")
            body = (node.get("body") or "")[:1500]
            content = f"{title}\n\n{body}".strip() if body else title
            author = (node.get("author") or {}).get("login") or ""
            posts.append({
                "external_id": f"gh-disc-{node_id}",
                "content": content,
                "source_url": node.get("url"),
                "author_name": None,
                "author_username": author or None,
                "author_url": f"https://github.com/{author}" if author else None,
            })
        log.info("GitHub discussion search '%s': %d results", query[:60], len(posts))
        return posts
    except Exception:
        log.exception("GitHub discussion search failed for '%s'", query[:60])
        return []


def fetch_posts(repo_or_topic: str, limit: int = 25) -> list[dict]:
    """
    Fetch issues from a specific repo (owner/repo format) or search by topic keyword.
    e.g. channel name 'vercel/next.js' → fetch issues for that repo.
         channel name 'nextjs' → search issues mentioning nextjs.
    """
    if "/" in repo_or_topic:
        # Specific repo
        try:
            resp = httpx.get(
                f"{_BASE}/repos/{repo_or_topic}/issues",
                params={"state": "open", "sort": "created", "per_page": min(limit, 30)},
                headers=_auth_headers(),
                timeout=15,
            )
            resp.raise_for_status()
            posts = [_build_post(item, "issue") for item in resp.json() if isinstance(item, dict)]
            log.info("GitHub repo '%s' issues: %d results", repo_or_topic, len(posts))
            return posts
        except Exception:
            log.exception("GitHub fetch failed for repo '%s'", repo_or_topic)
            return []
    else:
        return search_issues(repo_or_topic, limit=limit)
