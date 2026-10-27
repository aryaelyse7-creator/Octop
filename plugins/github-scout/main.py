"""GitHub Scout toolkit — search GitHub so the agent can shortlist repos and code.

Backed by the ``gh`` CLI (preinstalled and authenticated in GitHub Codespaces;
elsewhere run ``gh auth login`` once). All tools return JSON strings with a
``results`` list and an ``error`` field on failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil

from octop_harness.plugins import PluginContext

logger = logging.getLogger("octop.plugins.github_scout")

_MAX_RESULTS = 30
_MAX_DESC = 200
_MAX_README = 4000
_GH_TIMEOUT = 30.0


async def _gh(*args: str) -> tuple[int, str, str]:
    """Run a gh subcommand, returning (returncode, stdout, stderr)."""
    if shutil.which("gh") is None:
        return 127, "", "gh CLI not found on PATH"
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_GH_TIMEOUT)
    except TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        return 124, "", "gh timed out"
    except OSError as exc:
        return 126, "", str(exc)
    return (
        proc.returncode if proc.returncode is not None else 1,
        out.decode(errors="replace"),
        err.decode(errors="replace"),
    )


def _error(error: str) -> str:
    return json.dumps({"results": [], "error": error}, ensure_ascii=False)


async def github_search_repos(query: str, limit: int = 5, sort: str = "best-match") -> str:
    """Search GitHub repositories and return a shortlist.

    Query uses GitHub search syntax, e.g. "browser automation language:python"
    or "mcp server stars:>100". sort: best-match, stars, updated.
    """
    if not query.strip():
        return _error("query is required")
    limit = max(1, min(int(limit), _MAX_RESULTS))
    args = [
        "search",
        "repos",
        query,
        "--limit",
        str(limit),
        "--json",
        "fullName,description,stargazersCount,url,language,updatedAt",
    ]
    if sort in ("stars", "forks", "updated"):
        args += ["--sort", sort]
    code, out, err = await _gh(*args)
    if code != 0:
        return _error(err.strip() or f"gh search repos exited with {code}")
    try:
        rows = json.loads(out)
    except ValueError:
        return _error("could not parse gh output")
    results = [
        {
            "repo": row.get("fullName"),
            "stars": row.get("stargazersCount"),
            "language": row.get("language"),
            "description": (row.get("description") or "")[:_MAX_DESC],
            "url": row.get("url"),
            "updated": (row.get("updatedAt") or "")[:10],
        }
        for row in rows
    ]
    return json.dumps(
        {"query": query, "count": len(results), "results": results},
        ensure_ascii=False,
    )


async def github_search_code(query: str, limit: int = 5) -> str:
    """Search code across GitHub, e.g. "browser_use repo:TencentCloud/octop".

    Useful to find how a tool/library is actually used before adopting it.
    """
    if not query.strip():
        return _error("query is required")
    limit = max(1, min(int(limit), _MAX_RESULTS))
    code, out, err = await _gh(
        "search", "code", query, "--limit", str(limit), "--json", "path,repository,url"
    )
    if code != 0:
        return _error(err.strip() or f"gh search code exited with {code}")
    try:
        rows = json.loads(out)
    except ValueError:
        return _error("could not parse gh output")
    results = [
        {
            "repo": (row.get("repository") or {}).get("nameWithOwner"),
            "path": row.get("path"),
            "url": row.get("url"),
        }
        for row in rows
    ]
    return json.dumps(
        {"query": query, "count": len(results), "results": results},
        ensure_ascii=False,
    )


async def github_readme(repo: str) -> str:
    """Fetch a repo's README (truncated) to vet a shortlisted candidate."""
    if not repo.strip():
        return _error("repo is required (e.g. owner/name)")
    code, out, err = await _gh("repo", "view", repo.strip())
    if code != 0:
        return _error(err.strip() or f"gh repo view exited with {code}")
    return json.dumps(
        {"repo": repo.strip(), "readme": out[:_MAX_README], "truncated": len(out) > _MAX_README},
        ensure_ascii=False,
    )


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "github_search_repos",
        github_search_repos,
        description="Search GitHub repos and return a shortlist (name, stars, description, URL)",
    )
    ctx.tool(
        "github_search_code",
        github_search_code,
        description="Search code across GitHub to see how tools are used",
    )
    ctx.tool(
        "github_readme",
        github_readme,
        description="Fetch a repo's README (truncated) to evaluate it",
    )
