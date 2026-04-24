"""Template Hydration Engine for token-efficient AI orchestration.

Validates compressed LLM-generated JSON payloads against strict Pydantic
schemas and hydrates them into full boilerplate artefacts (Dockerfiles,
Kubernetes manifests, Python scripts) via Jinja2 templates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jinja2
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pydantic import BaseModel, ValidationError

logger: logging.Logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------------

class HydrationError(Exception):
    """Raised when payload validation or template rendering fails.

    Wraps the original ``json.JSONDecodeError`` or
    ``pydantic.ValidationError`` for clean upstream error handling without
    leaking implementation details.
    """

    def __init__(self, message: str, original: Exception | None = None) -> None:
        self.original: Exception | None = original
        super().__init__(message)


# ---------------------------------------------------------------------------
# Pydantic validation schemas
# ---------------------------------------------------------------------------

class AgentBlueprint(BaseModel):
    """Strict validation gate for incoming LLM-generated JSON payloads.

    Every field is required.  Additional fields are silently ignored
    (Pydantic default) so that the orchestrator can evolve without breaking
    existing templates.

    Attributes
    ----------
    agent_name:
        Human-readable identifier for the agent (e.g. ``"recon-scanner"``).
    version:
        Semantic version string (e.g. ``"1.3.0"``).
    dependencies:
        List of runtime dependency specifiers
        (e.g. ``["requests>=2.28", "rich"]``).
    env_vars:
        Mapping of environment variable names to their default values
        (e.g. ``{"LOG_LEVEL": "INFO", "PORT": "8080"}``).
    """

    agent_name: str
    version: str
    dependencies: list[str]
    env_vars: dict[str, str]


# ---------------------------------------------------------------------------
# Hydration engine
# ---------------------------------------------------------------------------

class HydrationEngine:
    """Validates compressed JSON payloads and renders Jinja2 templates.

    The engine is initialised once with a templates directory and an output
    directory.  Each call to :meth:`render_to_file` performs the full
    pipeline: JSON parse → Pydantic validation → template render → file
    write.

    Parameters
    ----------
    templates_dir:
        Directory containing ``.j2`` (or any) Jinja2 template files.
    output_dir:
        Directory where hydrated files will be written.  Created
        automatically if it does not exist.
    """

    def __init__(
        self,
        templates_dir: str | Path,
        output_dir: str | Path,
    ) -> None:
        self._templates_root: Path = Path(templates_dir)
        self._output_dir: Path = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._env: Environment = Environment(
            loader=FileSystemLoader(str(self._templates_root)),
            keep_trailing_newline=True,
            encoding="utf-8",
        )

    # -- private helpers ---------------------------------------------------

    def _validate_payload(self, raw_json: str) -> dict[str, Any]:
        """Parse and validate *raw_json* against :class:`AgentBlueprint`.

        Parameters
        ----------
        raw_json:
            Raw JSON string produced by the LLM.

        Returns
        -------
        dict[str, Any]
            The validated payload as a plain dictionary, safe for template
            rendering.

        Raises
        ------
        HydrationError
            If the JSON is malformed or fails Pydantic validation.
        """
        # ---- JSON parse ---------------------------------------------------
        try:
            parsed: Any = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            msg: str = f"Malformed JSON payload: {exc}"
            logger.critical(msg)
            raise HydrationError(msg, original=exc) from exc

        # ---- Pydantic validation ------------------------------------------
        try:
            blueprint: AgentBlueprint = AgentBlueprint.model_validate(parsed)
        except ValidationError as exc:
            msg = f"Payload failed AgentBlueprint validation: {exc}"
            logger.critical(msg)
            raise HydrationError(msg, original=exc) from exc

        return blueprint.model_dump()

    # -- public API ---------------------------------------------------------

    def render_to_file(
        self,
        template_name: str,
        raw_json: str,
        output_filename: str,
    ) -> bool:
        """Full hydration pipeline: validate → render → write.

        Parameters
        ----------
        template_name:
            Filename of the Jinja2 template inside *templates_dir*
            (e.g. ``"Dockerfile.j2"``).
        raw_json:
            Compressed JSON string from the LLM.
        output_filename:
            Name of the file to write in *output_dir*
            (e.g. ``"Dockerfile"``).

        Returns
        -------
        bool
            ``True`` on success, ``False`` on any failure (logged).
        """
        # ---- validate ------------------------------------------------------
        try:
            context: dict[str, Any] = self._validate_payload(raw_json)
        except HydrationError:
            return False

        # ---- load template -------------------------------------------------
        try:
            template: jinja2.Template = self._env.get_template(template_name)
        except TemplateNotFound:
            logger.critical("Template not found: %s", template_name)
            return False

        # ---- render --------------------------------------------------------
        try:
            rendered: str = template.render(**context)
        except jinja2.TemplateError as exc:
            logger.critical(
                "Template rendering failed for '%s': %s",
                template_name,
                exc,
            )
            return False

        # ---- write ---------------------------------------------------------
        target: Path = self._output_dir / output_filename
        try:
            target.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            logger.critical("Failed to write '%s': %s", target, exc)
            return False

        logger.info(
            "Hydrated '%s' → %s (%d bytes)",
            template_name,
            target,
            len(rendered.encode("utf-8")),
        )
        return True
