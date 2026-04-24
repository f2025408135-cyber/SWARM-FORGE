"""Geometric DOM Sanitizer — Perception Defense Layer (AgentGuard Layer 1).

Implements deterministic Content Injection Trap neutralization by leveraging
a headless Chromium browser to compute full CSSOM bounding boxes, physically
excising hidden DOM nodes before they reach the LLM context window.

Defeats: CSS display:none, visibility:hidden, opacity:0, off-screen positioning,
clip-path masking, and Shadow DOM payload smuggling.

Attack Success Rate reduction: 100% → 0.88% (per eBay Cognitive Firewall research, Mar 2026).

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import logging
from typing import Final

logger: logging.Logger = logging.getLogger(__name__)

PLAYWRIGHT_AVAILABLE: bool
try:
    from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning(
        "AgentGuard Layer 1: playwright or bs4 not installed. "
        "DOM sanitization degraded to raw HTML stripping."
    )

DEFAULT_TIMEOUT_MS: Final[int] = 15000
STEALTH_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

JS_EXCISION_ROUTINE: Final[str] = """
() => {
    let removedCount = 0;
    function processNode(node) {
        if (node.shadowRoot) { processNodeTree(node.shadowRoot); }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        const tag = node.tagName.toUpperCase();
        if (tag === 'HTML' || tag === 'BODY' || tag === 'HEAD') return;
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        const isHiddenCSS = style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
        const isZeroSize = rect.width === 0 || rect.height === 0;
        const isOffScreen = rect.right < 0 || rect.bottom < 0;
        const isClipped = style.clip === 'rect(0px, 0px, 0px, 0px)' || style.clipPath === 'inset(100%)';
        if (isHiddenCSS || isZeroSize || isOffScreen || isClipped) {
            node.remove(); removedCount++;
        }
    }
    function processNodeTree(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
        const nodes = [];
        let n = walker.nextNode();
        while (n) { nodes.push(n); n = walker.nextNode(); }
        for (let i = nodes.length - 1; i >= 0; i--) { processNode(nodes[i]); }
    }
    processNodeTree(document);
    return removedCount;
}
"""


class GeometricDOMSanitizer:
    """Headless-browser geometric perception filter for AgentGuard Layer 1.

    Uses Playwright/Chromium to compute full CSSOM render tree and excise
    any DOM nodes that are geometrically invisible to a human operator,
    preventing hidden prompt injections from reaching the LLM context window.

    Degrades gracefully to BeautifulSoup-only stripping if Playwright unavailable.
    """

    def __init__(
        self,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        stealth_mode: bool = True,
    ) -> None:
        """Initialize the sanitizer.

        Args:
            timeout_ms: Maximum milliseconds to wait for full page render.
            stealth_mode: If True, mimics standard browser user-agent to defeat
                bot detection.
        """
        self._timeout_ms: int = timeout_ms
        self._stealth_mode: bool = stealth_mode

    async def sanitize_payload(
        self, raw_html: str, base_url: str = "http://localhost"
    ) -> str:
        """Run the geometric excision pipeline on raw HTML.

        Args:
            raw_html: Raw HTML string from web scraper or tool call.
            base_url: Base URL for resolving relative assets during render.

        Returns:
            Geometrically sanitized HTML string with hidden nodes removed.
            Returns empty string on timeout (fail-closed).

        Raises:
            RuntimeError: If Playwright is unavailable and degraded mode fails.
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning(
                "GeometricDOMSanitizer: degraded mode — stripping raw HTML only."
            )
            return self._fallback_strip(raw_html)

        # Outer belt-and-suspenders guard: if async_playwright() itself crashes
        # (e.g. browser binary missing, OS fault), or chromium.launch() raises
        # before the inner try-block is reached, we MUST still fail-closed and
        # return "" rather than propagate raw unsanitized HTML back to callers.
        try:
            async with async_playwright() as p:
                launch_args = (
                    ["--disable-blink-features=AutomationControlled"]
                    if self._stealth_mode
                    else []
                )
                browser = await p.chromium.launch(headless=True, args=launch_args)
                ctx = await browser.new_context(
                    java_script_enabled=True,
                    bypass_csp=True,
                    user_agent=STEALTH_USER_AGENT,
                )
                page = await ctx.new_page()
                try:
                    await page.set_content(
                        raw_html, timeout=self._timeout_ms, wait_until="networkidle"
                    )
                    removed = await page.evaluate(JS_EXCISION_ROUTINE)
                    logger.info(
                        "GeometricDOMSanitizer: excised %d hidden nodes.", removed
                    )
                    return await page.content()
                except Exception:
                    logger.error(
                        "GeometricDOMSanitizer: render failed — payload dropped (fail-closed)."
                    )
                    return ""
                finally:
                    try:
                        await ctx.close()
                        await browser.close()
                    except Exception:
                        logger.warning(
                            "GeometricDOMSanitizer: teardown failed — process "
                            "continues fail-closed."
                        )
        except Exception:
            logger.error(
                "GeometricDOMSanitizer: Playwright bootstrap failed — "
                "payload dropped (fail-closed)."
            )
            return ""

    def extract_clean_text(self, sanitized_html: str) -> str:
        """Extract plain text from sanitized HTML using BeautifulSoup lxml parser.

        Args:
            sanitized_html: Geometrically sanitized HTML from sanitize_payload().

        Returns:
            Clean plain-text string safe for LLM ingestion.
        """
        if not sanitized_html:
            return ""
        if not PLAYWRIGHT_AVAILABLE:
            return self._fallback_strip(sanitized_html)
        soup = BeautifulSoup(sanitized_html, "lxml")
        for tag in soup(["script", "style", "noscript", "meta", "svg", "canvas"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)

    def _fallback_strip(self, html: str) -> str:
        """Degrade-mode: rudimentary regex strip when Playwright unavailable."""
        import re

        clean = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", clean).strip()
