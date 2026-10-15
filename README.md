# Launchpad Platform

Launchpad is a small Python developer platform that scaffolds independent HTTP service repositories. Each generated repository includes a runnable service, a container build, a restricted Helm chart, Argo CD configuration, GitHub Actions workflows, and explicit preview lifecycle commands.

The platform CLI itself uses only the Python standard library at runtime. It does not provision a cluster or cloud account. Preview deployment is an explicit, manually dispatched GitHub Actions workflow against a cluster you configure.

## Install and create a service

Use Python 3.12. In a Bash-compatible shell:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

mkdir -p services
launchpad init payments-api --repository Raidensec/payments-api --output-parent ./services
launchpad check ./services/payments-api
```

`launchpad init` requires an existing output parent, validates the DNS service name and GitHub `owner/repository`, rejects symbolic-link parents, and refuses to overwrite an existing service directory. Generated files are opened with exclusive creation. It does not run Git, Docker, Helm, or shell commands.

The generated service binds to `0.0.0.0:8000` by default and exposes `GET /`, `/healthz`, `/readyz`, and `/metrics`. For local access, set `HOST=127.0.0.1` before running it:

```bash
cd services/payments-api
HOST=127.0.0.1 PORT=8000 python -m service.app
```

The service uses the Python standard library. Its generated CI runs Ruff, dependency auditing, and Helm chart linting; it does not deploy the service.

## Render and preview plans

The chart fails closed until an immutable image digest is provided. After the generated repository's `Service CI` workflow publishes an image, copy the `sha256:...` digest from its run summary:

```bash
read -r -p "Published image digest (sha256:...): " IMAGE_DIGEST
launchpad render ./services/payments-api --digest "$IMAGE_DIGEST"
launchpad preview-plan payments-api --repository Raidensec/payments-api \
  --digest "$IMAGE_DIGEST" --pull-request 123
launchpad destroy-plan payments-api --repository Raidensec/payments-api \
  --pull-request 123
```

`render` requires Helm 3.19 or newer and prints local rendered YAML. The preview and destroy commands print JSON plans with `"mode": "plan-only"` and `"cluster_calls": false`; they do not deploy or delete resources. The actual preview workflow is `workflow_dispatch` only, checks out the repository's default branch, and requires the protected `preview` GitHub environment.

Generated repositories assume `main` is the default branch: service CI publishes images from `main`, and the Argo CD Application tracks `main`. If you choose another default branch, update both settings in the generated repository. Promotion and preview workflows check the repository's configured default branch dynamically.

See [operations](docs/operations.md) for image promotion, GitHub environment setup, and preview cleanup. See [architecture](docs/architecture.md) for trust boundaries and the deployment flow.

## Checks

The platform CI runs Ruff, Python bytecode compilation, `pip-audit`, then scaffolds a temporary service, checks its required files, and runs `helm lint` with a synthetic digest. That synthetic chart hash exists only to validate Helm syntax; it is not an image and must not be deployed. CI does not contact Kubernetes or AWS.

To run the platform's static checks locally after installing the development dependencies:

```bash
ruff check .
python -m compileall -q src
```

The chart checks and preview lifecycle require Helm or a GitHub environment respectively. No AWS infrastructure is included or started by this repository. The implementation does not claim production readiness; adapt resource budgets, ingress, network egress, registry access, and cluster policy to your environment before use.

## Repository layout

- `src/launchpad/` contains the CLI, input validation, safe scaffold writer, chart rendering, and plan generation.
- `src/launchpad/assets/` contains the generated service project templates.
- `.github/workflows/ci.yml` checks the platform package and generated chart without deploying infrastructure.
- `docs/` records the architecture and operational prerequisites.
