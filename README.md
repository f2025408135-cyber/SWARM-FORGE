# SWARM-FORGE

Deterministic, zero-trust agent orchestration kernel for Claude — the only orchestration framework architecturally capable of regulated deployment.

**Topological determinism · AST capability dropping · Fail-closed semantic verification.**

## Overview

SWARM-FORGE is a deterministic multi-agent orchestration framework that coordinates Claude agents through a mathematically verifiable execution topology. Every agent capability is statically verified before execution — no dynamic code paths, no ambient authority, no undefined behavior.

## Core Principles

### Topological Determinism
Every agent interaction is modeled as a finite state machine with explicit transitions. The execution graph is a DAG with no cycles — guaranteeing termination.

### AST Capability Dropping
Agent capabilities are defined as an abstract syntax tree and statically verified against a policy before execution. Any unverifiable capability is dropped — fail-closed by default.

### Fail-Closed Semantic Verification
Every agent output is semantically verified against the expected schema. Invalid outputs are rejected, not coerced. The pipeline halts on any semantic violation.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  SWARM-FORGE                         │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │   Agent A   │  │   Agent B   │  │  Agent C   │  │
│  │ (Research)  │  │  (Coding)   │  │ (Review)   │  │
│  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘  │
│         │                │               │          │
│  ───────┴────────────────┴───────────────┴──────    │
│  │         Execution Topology (DAG)                  │
│  ───────┬────────────────┬───────────────┬──────    │
│         │                │               │          │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐  │
│  │   Policy     │  │  Semantic   │  │  Output    │  │
│  │   Engine     │  │  Verifier   │  │  Queue     │  │
│  │ (AST Check)  │  │ (Schema)    │  │            │  │
│  └─────────────┘  └─────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Features

- **Deterministic execution** — same inputs + same topology = identical outputs
- **Static capability verification** — agent capabilities verified before execution
- **Semantic output validation** — every output validated against schema
- **Zero-trust architecture** — no ambient authority, explicit grants only
- **Regulated deployment ready** — audit trails, policy enforcement, fail-closed defaults

## Installation

```bash
git clone https://github.com/f2025408135-cyber/SWARM-FORGE.git
cd SWARM-FORGE
npm install
```

## Usage

### Define an Agent Topology

```yaml
# topology.yaml
agents:
  researcher:
    type: claude
    model: claude-opus-4-7
    capabilities: ["web_search", "file_read"]
    policy: "read_only"
    
  coder:
    type: claude
    model: claude-opus-4-7
    capabilities: ["code_generate", "file_write"]
    policy: "code_gen_restricted"
    depends_on: ["researcher"]
    
  reviewer:
    type: claude
    model: claude-opus-4-7
    capabilities: ["file_read", "code_review"]
    policy: "review_only"
    depends_on: ["coder"]

tasks:
  research:
    agent: researcher
    input: "Research the security implications of X"
    
  implement:
    agent: coder
    input: "Implement a solution for X"
    context_from: ["research"]
    
  review:
    agent: reviewer
    input: "Review the implementation"
    context_from: ["implement"]
```

### Run the Topology

```bash
npx swarm-forge run --topology topology.yaml
```

### Verify Before Execution

```bash
npx swarm-forge verify --topology topology.yaml
# → Validates all agent capabilities against policies
# → Reports any dropped capabilities
# → Outputs execution plan
```

## Policy Engine

Policies define what each agent can and cannot do:

```yaml
# policies.yaml
policies:
  read_only:
    allow: ["web_search", "file_read", "web_fetch"]
    deny: ["file_write", "code_exec", "api_write"]
    
  code_gen_restricted:
    allow: ["code_generate", "file_read"]
    deny: ["file_write", "network_write", "shell_exec"]
    constraints:
      max_file_size: "100KB"
      allowed_languages: ["python", "typescript"]
      forbidden_imports: ["subprocess", "os.system"]
    
  review_only:
    allow: ["file_read", "code_review"]
    deny: ["file_write", "code_generate"]
```

## Project Structure

```
SWARM-FORGE/
├── lib/
│   ├── api-server/         # REST API for topology management
│   ├── api-client-react/   # React client library
│   ├── api-spec/           # OpenAPI specification
│   ├── api-zod/            # Zod schema validators
│   └── db/                 # Persistence layer
├── scripts/
│   └── src/                # Build and deployment scripts
├── swarm_service/          # Core orchestration service
│   └── .claude/            # Claude agent definitions
├── artifacts/
│   ├── api-server/         # API server artifacts
│   ├── mockup-sandbox/     # Sandbox environment
│   └── swarm-ui/           # Web UI
├── package.json
└── pnpm-workspace.yaml
```

## Development

```bash
# Install dependencies
pnpm install

# Run in development
pnpm dev

# Build
pnpm build

# Run tests
pnpm test
```

## Security Model

| Layer | Mechanism |
|---|---|
| Authentication | OAuth 2.0 / OIDC |
| Authorization | RBAC with policy engine |
| Capability Verification | AST-based static analysis |
| Output Validation | Schema-based semantic verification |
| Audit | Immutable execution log |

## License

MIT
