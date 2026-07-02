# CI Hermetic Toolchain Doctrine

**CI-HERMETIC-TOOLCACHE**

## Intent

k9b CI is intentionally **shell-first** and **toolcache-first**. The goal is reproducible, auditable tool resolution that does not depend on mutable external downloads at runtime.

## Core Principles

### Shell-first over uses:

Prefer `run:` shell steps over `uses:` actions wherever a pinned runner tool-cache path or a checked-in script achieves the same result.

### Toolcache-first over setup/download

Prefer runner/tool-cache binaries over setup/download actions. GitHub-hosted runners ship a pre-populated tool cache (`$RUNNER_TOOL_CACHE` / `$AGENT_TOOLSDIRECTORY`) containing Python, Go, Node, Helm, kubectl, and other common tooling. Calling these binaries directly via `run:` avoids the mutable, network-dependent behavior of setup actions.

### Fail fast on missing tools

Cached tools must be verified at job start. Missing cached tools must fail fast, not silently download mutable replacements. A missing tool is a configuration error that should surface immediately, not a runtime surprise.

### Python startup proof (not just .complete markers)

For Python environments, a `.complete` marker in the toolcache directory is not sufficient proof of usability. The Python wiring must include:

- `LD_LIBRARY_PATH` for shared library linking (`libpython*.so*`)
- `python3 -VV` to prove executable startup
- `sys.executable` to verify the executable path
- SSL/TLS import proof where HTTPS is required

### Contract roots

- `$RUNNER_TOOL_CACHE` (GitHub Actions variable)
- `$AGENT_TOOLSDIRECTORY` (alternative tooling directory variable)

## Allowed vs. Forbidden

| Pattern | Status | Rationale |
|---------|--------|-----------|
| `actions/checkout` | Allowed | Essential for repo access |
| `actions/cache` | Allowed | Explicit caching infrastructure |
| `actions/download-artifact`, `actions/upload-artifact` | Allowed | Build artifact management |
| `actions/github-script` | Allowed | Workflow automation |
| `actions/setup-python` | **Forbidden** | Mutable download; use `run: python3` or toolcache |
| `actions/setup-node` | **Forbidden** | Mutable download; use `run: node` or toolcache |
| `actions/setup-go` | **Forbidden** | Mutable download; use `run: go` or toolcache |
| `actions/setup-java` | **Forbidden** | Mutable download; use toolcache |
| `actions/setup-kubectl` | **Forbidden** | Mutable download; use `run: kubectl` |
| `azure/setup-helm` | **Temporary exception** | Helm setup; migrate to toolcache-first |
| `docker/setup-*` | **Temporary exception** | Container build; migrate to toolcache-first |
| `docker/login-*` | **Temporary exception** | Container registry auth; migrate to toolcache-first |
| `helm/*` actions | **Temporary exception** | Helm operations; migrate to toolcache-first |
| Repo-local actions (`./`) | Allowed | Local, version-controlled actions |

## Toolcache Binary Verification

Before assuming a toolcache binary is available, verify it:

```bash
# Python startup proof
export LD_LIBRARY_PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))'):$LD_LIBRARY_PATH"
python3 -VV
python3 -c "import sys; print(sys.executable)"
python3 -c "import ssl; print('SSL OK')"

# Helm verification
helm version --short

# kubectl verification
kubectl version --client | head -1
```

## Rationale

Setup/download actions (e.g., `actions/setup-python`) fetch mutable versions of tools at runtime. This creates several risks:

1. **Non-reproducibility**: Different runs may get different tool versions
2. **Network dependency**: Runs fail if PyPI/npm/etc. is unreachable
3. **Supply chain**: Mutable downloads are harder to audit than pinned toolcache binaries
4. **Latency**: Downloads add minutes to job runtime

The runner toolcache is pre-populated with pinned versions of common tools. Using these directly via `run:` shell steps is faster, more reproducible, and easier to audit.

## Exceptions

Exceptions to this doctrine require explicit documentation in the workflow file and must be approved by a platform lead. Acceptable exceptions include:

- Tools not available in the runner toolcache
- Version pinned via `actions/setup-*` with explicit `with: version:` constraints
- One-time bootstrapping steps (e.g., installing a tool not in the toolcache)

## See Also

- `$RUNNER_TOOL_CACHE` documentation in GitHub Actions
- `$AGENT_TOOLSDIRECTORY` for self-hosted runners
- `tests/test_github_actions_hermetic_toolchain_policy.py` for the policy gate
