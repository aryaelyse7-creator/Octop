"""Browser Driver toolkit — drive a real Chrome via CDP from the agent.

Thin, agent-friendly wrappers over ``octop_browser.tool_interface.browser_tool``
(the same engine behind the built-in ``browser_use`` tool), plus explicit
copy/paste verbs. Sessions persist per ``profile`` (cookies, logins kept on
disk). Browser mode resolves automatically: headed on desktops, headless in
containers/codespaces without a display.

Authoring notes (see plugins/README.md):
- Tool functions are async, parameters become the agent call schema.
- All tools return JSON strings with a ``success`` flag and ``error`` field.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from octop_browser.tool_interface import browser_tool
from octop_harness.plugins import PluginContext

logger = logging.getLogger("octop.plugins.browser_driver")

_MAX_COPIED_TEXT = 20000


def _payload(result: Any) -> str:
    """Serialize a ToolResult into a compact JSON envelope for the agent."""
    out: dict[str, Any] = {
        "success": result.success,
        "content": result.content,
        "error": result.error,
    }
    if result.metadata:
        out["metadata"] = result.metadata
    return json.dumps(out, ensure_ascii=False)


async def browser_navigate(url: str, new_tab: bool = False, profile: str = "default") -> str:
    """Open a URL in the browser. Set new_tab=true to open it in a separate tab."""
    action = "new_tab" if new_tab else "navigate"
    return _payload(await browser_tool(action, profile=profile, url=url))


async def browser_read(profile: str = "default", level: str = "interactive") -> str:
    """Read the current page as a structured DOM snapshot with clickable refs.

    Returns element refs (like ``e12``) to pass to browser_click/browser_type.
    Use level=full for a more verbose snapshot.
    """
    return _payload(await browser_tool("dom_tree", profile=profile, level=level))


async def browser_click(
    ref: str | None = None,
    selector: str | None = None,
    x: int | None = None,
    y: int | None = None,
    profile: str = "default",
) -> str:
    """Click an element by ref (from browser_read), CSS selector, or coordinates."""
    return _payload(
        await browser_tool("click", profile=profile, ref=ref, selector=selector, x=x, y=y)
    )


async def browser_type(
    text: str,
    ref: str | None = None,
    selector: str | None = None,
    clear_first: bool = False,
    profile: str = "default",
) -> str:
    """Type text, optionally clicking the target field first (ref or selector).

    clear_first=true replaces existing content (uses fill instead of type).
    """
    action = "fill" if clear_first else "type"
    return _payload(
        await browser_tool(action, profile=profile, text=text, ref=ref, selector=selector)
    )


async def browser_press(key: str, profile: str = "default") -> str:
    """Press a keyboard key in the page: Enter, Tab, Escape, Backspace, etc."""
    return _payload(await browser_tool("press", profile=profile, key=key))


async def browser_copy(selector: str | None = None, profile: str = "default") -> str:
    """Copy text to the clipboard: an element (CSS selector) or the whole page.

    Selects the target, issues a real copy, and returns the copied text so the
    agent knows exactly what is on the clipboard.
    """
    sel = json.dumps(selector)
    expression = (
        "(() => {"
        f"  const target = ({sel}) ? document.querySelector({sel}) : document.body;"
        "  if (!target) return JSON.stringify({ok: false, text: '', error: 'selector"
        " matched nothing'});"
        "  const s = window.getSelection(); s.removeAllRanges();"
        "  const r = document.createRange(); r.selectNodeContents(target);"
        "  s.addRange(r);"
        "  const ok = document.execCommand('copy');"
        "  const text = s.toString(); s.removeAllRanges();"
        "  return JSON.stringify({ok: ok, text: text});"
        "})()"
    )
    result = await browser_tool("eval_js", profile=profile, expression=expression)
    if not result.success:
        return _payload(result)
    try:
        inner: Any = json.loads(str(result.content))
        if isinstance(inner, str):  # CDP double-encodes stringified values
            inner = json.loads(inner)
    except (TypeError, ValueError):
        return _payload(result)
    if not isinstance(inner, dict):
        return _payload(result)
    copied = str(inner.get("text", ""))[:_MAX_COPIED_TEXT]
    return json.dumps(
        {
            "success": bool(inner.get("ok")) or bool(copied),
            "copied_chars": len(copied),
            "clipboard": copied,
            "error": inner.get("error"),
        },
        ensure_ascii=False,
    )


async def browser_paste(text: str, selector: str | None = None, profile: str = "default") -> str:
    """Paste text into a page field: focuses the target (selector) and inserts text.

    This is the reliable paste path (real Ctrl+V is not dispatchable over CDP
    without modifiers); text is inserted exactly as provided.
    """
    return _payload(await browser_tool("type", profile=profile, text=text, selector=selector))


async def browser_screenshot(
    full_page: bool = False, path: str | None = None, profile: str = "default"
) -> str:
    """Capture a screenshot PNG and return the file path. Use full_page sparingly."""
    return _payload(
        await browser_tool("screenshot", profile=profile, full_page=full_page, path=path)
    )


async def browser_scroll(
    direction: str = "down", amount: int = 300, profile: str = "default"
) -> str:
    """Scroll the page: direction=up|down, amount in pixels."""
    return _payload(
        await browser_tool("scroll", profile=profile, direction=direction, amount=amount)
    )


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "browser_navigate",
        browser_navigate,
        description="Open a URL in the browser (optionally in a new tab)",
    )
    ctx.tool(
        "browser_read",
        browser_read,
        description="Read the current page as a DOM snapshot with clickable refs",
    )
    ctx.tool(
        "browser_click",
        browser_click,
        description="Click an element by ref, CSS selector, or coordinates",
    )
    ctx.tool(
        "browser_type",
        browser_type,
        description="Type text into a field (ref or CSS selector), optionally clearing it first",
    )
    ctx.tool(
        "browser_press",
        browser_press,
        description="Press a keyboard key (Enter, Tab, Escape, Backspace)",
    )
    ctx.tool(
        "browser_copy",
        browser_copy,
        description="Copy an element's or the page's text to the clipboard and return it",
    )
    ctx.tool(
        "browser_paste",
        browser_paste,
        description="Paste text into a page field by CSS selector",
    )
    ctx.tool(
        "browser_screenshot",
        browser_screenshot,
        description="Take a screenshot and return the PNG file path",
    )
    ctx.tool(
        "browser_scroll",
        browser_scroll,
        description="Scroll the page up/down by pixels",
    )
