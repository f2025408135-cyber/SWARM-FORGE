"""Tests for Jinja2 template library — verify all templates load without syntax errors."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError


_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "templates"


@pytest.fixture()
def env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), trim_blocks=True, lstrip_blocks=True)


# ── Template loading (syntax only) ─────────────────────────────────────────


class TestTemplateLoading:
    """Every template must parse without a TemplateSyntaxError."""

    @pytest.mark.parametrize(
        "template_name",
        [
            "agent_node.py.j2",
            "mcp_server.py.j2",
            "Dockerfile.j2",
            "kubernetes_deployment.yaml.j2",
            "github_actions_ci.yaml.j2",
        ],
    )
    def test_template_loads_without_error(self, env: Environment, template_name: str) -> None:
        """Jinja2 Environment.get_template must not raise TemplateSyntaxError."""
        template = env.get_template(template_name)
        assert template is not None
        assert template.name == template_name


# ── Agent Node Template ────────────────────────────────────────────────────


class TestAgentNodeTemplate:
    """Verify agent_node.py.j2 renders a complete Python module."""

    def _render(self, env: Environment, **kwargs) -> str:
        defaults: dict = {
            "agent_name": "test_researcher",
            "version": "0.1.0",
            "role": "researcher",
            "generated_at": "2025-01-01T00:00:00Z",
            "system_prompt": "You are a research agent.",
            "token_budget": 50000,
            "constraints": ["No hallucination", "Cite sources"],
            "tools": [
                {
                    "name": "web_search",
                    "signature": "query: str, limit: int = 10",
                    "description": "Search the web for information",
                },
            ],
            "model_tier": "SONNET",
            "max_tokens": 2048,
        }
        defaults.update(kwargs)
        return env.get_template("agent_node.py.j2").render(**defaults)

    def test_render_contains_agent_name(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "test_researcher" in rendered

    def test_render_contains_execute_function(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "async def execute(contract: NodeInputContract)" in rendered

    def test_render_contains_tool(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "async def web_search" in rendered

    def test_render_no_tools(self, env: Environment) -> None:
        rendered = self._render(env, tools=[])
        assert "@mcp.tool()" not in rendered
        assert "async def execute" in rendered

    def test_render_contains_constraints(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "- No hallucination" in rendered
        assert "- Cite sources" in rendered


# ── MCP Server Template ────────────────────────────────────────────────────


class TestMCPServerTemplate:
    """Verify mcp_server.py.j2 renders a FastMCP server module."""

    def _render(self, env: Environment, **kwargs) -> str:
        defaults: dict = {
            "server_name": "research_tools",
            "base_url": "http://localhost:8001",
            "auth_scheme": "bearer",
            "tools": [
                {
                    "tool_name": "web_search",
                    "description": "Search across indexed documents for recent information",
                    "parameters": {"query": "str", "limit": "int"},
                    "http_method": "POST",
                    "endpoint_path": "/api/search",
                },
            ],
        }
        defaults.update(kwargs)
        return env.get_template("mcp_server.py.j2").render(**defaults)

    def test_render_bearer_auth(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "Bearer" in rendered
        assert "RESEARCH_TOOLS_TOKEN" in rendered

    def test_render_api_key_auth(self, env: Environment) -> None:
        rendered = self._render(env, auth_scheme="api_key")
        assert "X-Api-Key" in rendered
        assert "RESEARCH_TOOLS_API_KEY" in rendered

    def test_render_no_auth(self, env: Environment) -> None:
        rendered = self._render(env, auth_scheme="none")
        assert "Content-Type" in rendered
        assert "Bearer" not in rendered
        assert "X-Api-Key" not in rendered

    def test_render_tool_with_post_body(self, env: Environment) -> None:
        rendered = self._render(env)
        assert 'await client.post(' in rendered
        assert "json=" in rendered

    def test_render_tool_get_no_body(self, env: Environment) -> None:
        rendered = self._render(
            env,
            tools=[{
                "tool_name": "status_check",
                "description": "Check system health status endpoint",
                "parameters": {},
                "http_method": "GET",
                "endpoint_path": "/api/status",
            }],
        )
        assert 'await client.get(' in rendered
        assert "json=" not in rendered

    def test_render_input_model(self, env: Environment) -> None:
        rendered = self._render(env)
        # Jinja2 title filter capitalises first char of the whole string only
        assert "class Web_searchInput(BaseModel):" in rendered
        assert "query: str" in rendered

    def test_render_no_tools(self, env: Environment) -> None:
        rendered = self._render(env, tools=[])
        assert "@mcp.tool()" not in rendered
        assert "mcp.run()" in rendered


# ── Dockerfile Template ────────────────────────────────────────────────────


class TestDockerfileTemplate:
    """Verify Dockerfile.j2 renders a multi-stage Docker build."""

    def _render(self, env: Environment, **kwargs) -> str:
        defaults: dict = {
            "agent_name": "executor_agent",
            "version": "1.0.0",
            "dependencies": ["pydantic>=2.0.0", "httpx>=0.25.0"],
            "env_vars": {"LOG_LEVEL": "INFO", "MODEL_TIER": "sonnet"},
        }
        defaults.update(kwargs)
        return env.get_template("Dockerfile.j2").render(**defaults)

    def test_render_multi_stage(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "AS builder" in rendered
        assert "distroless" in rendered

    def test_render_dependencies(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "pydantic>=2.0.0" in rendered
        assert "httpx>=0.25.0" in rendered

    def test_render_env_vars(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "ENV LOG_LEVEL=INFO" in rendered
        assert "ENV MODEL_TIER=sonnet" in rendered

    def test_render_no_env_vars(self, env: Environment) -> None:
        rendered = self._render(env, env_vars={})
        assert "CMD" in rendered

    def test_render_no_dependencies(self, env: Environment) -> None:
        rendered = self._render(env, dependencies=[])
        assert "fastmcp>=0.3.0" in rendered  # always included
        assert "anthropic>=0.40.0" in rendered

    def test_render_nonroot_user(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "USER 65532:65532" in rendered


# ── Kubernetes Deployment Template ─────────────────────────────────────────


class TestKubernetesDeploymentTemplate:
    """Verify kubernetes_deployment.yaml.j2 renders valid K8s manifests."""

    def _render(self, env: Environment, **kwargs) -> str:
        defaults: dict = {
            "agent_name": "research_agent",
            "session_id": "sess-abc123",
            "role": "researcher",
            "version": "1.0.0",
            "image_name": "gcr.io/swarm-forge/research-agent",
        }
        defaults.update(kwargs)
        return env.get_template("kubernetes_deployment.yaml.j2").render(**defaults)

    def test_render_deployment_kind(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "kind: Deployment" in rendered

    def test_render_service_kind(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "kind: Service" in rendered

    def test_render_underscore_replaced(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "research-agent" in rendered
        assert "research_agent" not in rendered.split("kind:")[0]

    def test_render_session_label(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "sess-abc123" in rendered

    def test_render_custom_replicas(self, env: Environment) -> None:
        rendered = self._render(env, replicas=3)
        assert "replicas: 3" in rendered

    def test_render_default_replicas(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "replicas: 1" in rendered

    def test_render_health_probes(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "/healthz/ready" in rendered
        assert "/healthz/semantic" in rendered

    def test_render_resource_defaults(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "256Mi" in rendered
        assert "100m" in rendered
        assert "512Mi" in rendered
        assert "500m" in rendered

    def test_render_custom_resources(self, env: Environment) -> None:
        rendered = self._render(
            env,
            memory_request="512Mi", cpu_request="250m",
            memory_limit="1Gi", cpu_limit="1000m",
        )
        assert "512Mi" in rendered
        assert "1Gi" in rendered
        assert "1000m" in rendered


# ── GitHub Actions CI Template ─────────────────────────────────────────────


class TestGithubActionsCITemplate:
    """Verify github_actions_ci.yaml.j2 renders a CI pipeline."""

    def _render(self, env: Environment, **kwargs) -> str:
        defaults: dict = {
            "swarm_name": "data-pipeline-swarm",
        }
        defaults.update(kwargs)
        return env.get_template("github_actions_ci.yaml.j2").render(**defaults)

    def test_render_swarm_name(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "data-pipeline-swarm" in rendered

    def test_render_github_sha_expression(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "${{ github.sha }}" in rendered

    def test_render_python_version(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "3.12" in rendered

    def test_render_schema_validation_step(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "pytest tests/test_schemas.py" in rendered

    def test_render_staging_deploy(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "swarm-forge-staging" in rendered
        assert "helm upgrade --install" in rendered

    def test_render_gcp_workload_identity(self, env: Environment) -> None:
        rendered = self._render(env)
        assert "${{ secrets.GCP_WORKLOAD_IDENTITY }}" in rendered
