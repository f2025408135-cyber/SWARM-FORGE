"""Synaptic Garbage Collector — self-compressing memory layer for agent directives.

Provides :class:`SynapticGarbageCollector`, which manages a single file as a
living memory store for operational lessons and immunity directives. When the
file grows beyond a token budget, a "Sawtooth Collapse" is triggered: the
Anthropic Sonnet API performs a mark-and-sweep compression that distils bloated
error traces into dense, high-level architectural directives.

Example:
    >>> sgc = SynapticGarbageCollector(token_threshold=4000)
    >>> sgc.commit_and_prune("node_42", "MemoryError in matrix allocation")

Part of the Swarm-Forge autonomous multi-agent orchestration framework.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import anthropic
from filelock import FileLock

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False

logger: logging.Logger = logging.getLogger(__name__)

MODEL_SONNET: Final[str] = "claude-sonnet-4-5"
MAX_TOKENS_COMPRESS: Final[int] = 2048
ENV_API_KEY: Final[str] = "ANTHROPIC_API_KEY"

DIRECTIVE_OPEN: Final[str] = "{# DIRECTIVE BLOCK — IMMUNITY LESSON\n"
DIRECTIVE_CLOSE: Final[str] = "END DIRECTIVE BLOCK #}\n"

_COMPRESSION_SYSTEM: Final[str] = (
    "You are an Epistemic Compression Engine. This file contains bloated, "
    "repetitive operational rules and error traces. Perform a Mark-and-Sweep "
    "garbage collection. Identify the core architectural principles, delete "
    "outdated/contradicting traces, and compress this into a dense, high-level "
    "directive list. Output ONLY the compressed markdown."
)


class SynapticGarbageCollector:
    """Self-compressing memory manager for agent immunity directives.

    Manages a single file as a living memory store. Each call to
    :meth:`commit_and_prune` appends a structured error trace to the file.
    Once the estimated token count crosses *token_threshold*, a "Sawtooth
    Collapse" is triggered: the Anthropic Sonnet model compresses the entire
    file into a dense directive list, which replaces the old content before
    the new trace is appended.

    New traces are wrapped in Jinja2 comment blocks (``{# ... #}``) so that
    the file remains valid as a Jinja2 template while accumulating operational
    memory that the SGC can later read and compress.

    Attributes:
        _token_threshold: Max estimated tokens before compression fires.
        _template_path: Managed memory file path (resolved at call time).
        _client: Lazy-initialised Anthropic client; ``None`` until first use.
    """

    def __init__(
        self,
        token_threshold: int = 4000,
        template_path: str = "templates/agent_config.j2",
    ) -> None:
        """Store SGC parameters; defer API client construction to first use.

        Args:
            token_threshold: Estimated-token budget. Compression fires when
                ``self._estimate_tokens(file_content) >= token_threshold``.
            template_path: Path to the managed memory file. Relative paths are
                resolved against the current working directory at call time.
        """
        self._token_threshold: int = token_threshold
        self._template_path: str = template_path
        self._client: anthropic.Anthropic | None = None

    # ── public ─────────────────────────────────────────────────────────────

    def commit_and_prune(self, node_id: str, error_trace: str) -> None:
        """Append *error_trace* to the memory file, compressing if over budget.

        Reads the managed file, estimates its token footprint, and either
        appends the new trace inside a Jinja2 comment directive block or
        triggers a Sawtooth Collapse: the Sonnet API compresses the full
        content, the file is overwritten with the dense result, and *then*
        the new trace is appended.

        File writes are serialised with a ``FileLock`` co-located alongside
        the managed file so concurrent DAG workers cannot corrupt the store.

        Args:
            node_id: DAG node identifier used to label the directive entry.
            error_trace: Compressed error/analysis text to persist.
        """
        path: Path = Path(self._template_path)
        lock_path: str = str(path) + ".lock"

        with FileLock(lock_path):
            content: str = path.read_text(encoding="utf-8") if path.exists() else ""
            estimated_tokens: int = self._estimate_tokens(content)

            if estimated_tokens >= self._token_threshold:
                logger.info(
                    "SGC Sawtooth Collapse triggered — path=%s tokens≈%d",
                    path,
                    estimated_tokens,
                )
                compressed: str = self._sawtooth_collapse(content)
                path.write_text(compressed, encoding="utf-8")
                logger.info("SGC compression complete — path=%s", path)

            directive: str = self._format_directive(node_id, error_trace)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(directive)

        logger.info(
            "SGC lesson committed — node=%s path=%s tokens_before≈%d",
            node_id,
            path,
            estimated_tokens,
        )

    # ── private ────────────────────────────────────────────────────────────

    def _estimate_tokens(self, content: str) -> int:
        """Return an exact token count for *content* using tiktoken when available.

        Falls back to the ``len(content) // 4`` heuristic only when the
        ``tiktoken`` package is unavailable at import time. The cl100k_base
        encoding is used because it is a close proxy for Anthropic tokenisation
        and is stable across releases.

        Args:
            content: Raw text whose token footprint should be estimated.

        Returns:
            The token count (exact under tiktoken, approximate under fallback).
        """
        if _TIKTOKEN_AVAILABLE:
            return len(tiktoken.get_encoding("cl100k_base").encode(content))
        return len(content) // 4

    def _sawtooth_collapse(self, content: str) -> str:
        """Call the Anthropic Sonnet API to compress *content* into directives.

        Fail-open: if the API call fails for any reason, the original content
        is returned unchanged so the new trace can still be appended safely.

        Args:
            content: Full text of the memory file before compression.

        Returns:
            Compressed markdown from the API, or *content* unchanged on error.
        """
        try:
            client: anthropic.Anthropic = self._get_client()
            response = client.messages.create(
                model=MODEL_SONNET,
                max_tokens=MAX_TOKENS_COMPRESS,
                system=[
                    {
                        "type": "text",
                        "text": _COMPRESSION_SYSTEM,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": content}],
            )
            compressed: str = response.content[0].text.strip()
            logger.debug(
                "SGC compressed %d chars → %d chars", len(content), len(compressed)
            )
            return compressed + "\n"
        except anthropic.APIError as exc:
            logger.warning(
                "SGC Sawtooth Collapse API error — skipping compression: %s", exc
            )
            return content
        except Exception as exc:
            logger.warning(
                "SGC Sawtooth Collapse unexpected error — skipping compression: %s", exc
            )
            return content

    def _get_client(self) -> anthropic.Anthropic:
        """Return the cached Anthropic client, constructing it on first call.

        Returns:
            Authenticated :class:`anthropic.Anthropic` client.

        Raises:
            EnvironmentError: If ``ANTHROPIC_API_KEY`` is not set.
        """
        if self._client is None:
            api_key: str | None = os.environ.get(ENV_API_KEY)
            if not api_key:
                raise EnvironmentError(
                    f"{ENV_API_KEY} environment variable is not set"
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    @staticmethod
    def _format_directive(node_id: str, error_trace: str) -> str:
        """Format *error_trace* as a Jinja2 comment directive block.

        Args:
            node_id: DAG node identifier for the label.
            error_trace: Raw error/analysis text.

        Returns:
            A newline-terminated string safe to append to a Jinja2 template.
        """
        timestamp: str = datetime.now(timezone.utc).isoformat()
        return (
            f"\n{DIRECTIVE_OPEN}"
            f"Node: {node_id}\n"
            f"Timestamp: {timestamp}\n"
            f"Trace: {error_trace}\n"
            f"{DIRECTIVE_CLOSE}"
        )
