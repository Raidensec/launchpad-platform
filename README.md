# Launchpad Platform

Launchpad turns a service name and GitHub repository into a service project you can inspect before deciding how to ship it. Start by generating the files and checking the result; when you have a published image digest, render the chart locally before promoting it.

## Create a service

With Python 3.12, install the CLI from this repository and create a project under an existing directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

mkdir -p services
launchpad init payments-api --repository Raidensec/payments-api --output-parent ./services
launchpad check ./services/payments-api
```

`init` writes a new `payments-api` directory. `check` validates its project metadata and required files. The generated directory includes:

- `service/`: a small Python HTTP service with `/`, `/healthz`, `/readyz`, and `/metrics` endpoints.
- `Dockerfile`: builds the service image.
- `deploy/chart/`: a Helm chart whose workload uses an immutable image digest.
- `deploy/gitops/application.yaml`: an Argo CD Application configured to follow the `main` branch.
- `.github/workflows/`: service CI and separate image-promotion and preview workflows.
- `scripts/`: the generated workflow helpers for promotion and preview lifecycle operations.

The service uses Python's standard library and listens on `0.0.0.0:8000` by default. To run it locally, set a loopback address:

```bash
cd services/payments-api
HOST=127.0.0.1 PORT=8000 python -m service.app
```

After stopping the service with Ctrl-C, return to the platform repository root with `cd ../..` before continuing. The render and plan commands below use paths relative to that root.

## Render with an image digest

The chart starts with an empty digest and fails closed until it receives an immutable `sha256` digest. The generated `Service CI` workflow validates pull requests and pushes to `main`; after a validated push to `main`, it builds and publishes the image to GHCR and records its digest in the workflow summary.

Use that digest to render the chart locally. `launchpad render` requires Helm 3.19 or newer and prints rendered YAML:

```bash
read -r -p "Published image digest (sha256:...): " IMAGE_DIGEST
launchpad render ./services/payments-api --digest "$IMAGE_DIGEST"
```

The generated `Promote image digest` workflow can then be dispatched from the default branch. With a protected `promotion` environment configured, it updates the chart's digest and opens a pull request. The generated Argo CD Application tracks `main`; after the promotion pull request is merged, Argo CD can reconcile the committed chart values in an environment where Argo CD is configured.

The generated workflows assume `main` is the repository's default branch for image publishing and the Argo CD `targetRevision`. If you use another default branch, update both settings in the generated repository. Promotion and preview dispatches use the configured default branch.

## Plan and run a preview

These CLI commands describe preview operations as JSON:

```bash
launchpad preview-plan payments-api --repository Raidensec/payments-api \
  --digest "$IMAGE_DIGEST" --pull-request 123
launchpad destroy-plan payments-api --repository Raidensec/payments-api \
  --pull-request 123
```

Both plans report `"mode": "plan-only"` and `"cluster_calls": false`. They do not contact Kubernetes. To create or remove a preview, the generated `Preview` workflow must be started manually with `workflow_dispatch` from the default branch. Configure its `preview` GitHub environment to require approval and provide the cluster credential as `KUBECONFIG_B64`. A deploy uses a published image digest; a destroy checks the namespace ownership metadata before removing it.

See [operations](docs/operations.md) for the environment setup and lifecycle steps, and [architecture](docs/architecture.md) for the deployment flow and trust boundaries.

## Platform checks

The platform repository's CI runs Ruff, Python bytecode compilation, and `pip-audit`, then scaffolds and checks a temporary service and lints and renders its chart. The chart commands use a synthetic digest derived from `Chart.yaml` so the chart can be validated before any image exists. That value is only a validation fixture.

These checks do not publish an image or exercise Kubernetes, AWS, a preview, or an Argo CD sync. Image publishing and previews use generated repository workflows; a live sync also depends on Argo CD and cluster configuration outside this repository.

To run the local Python checks after installing the development dependencies:

```bash
ruff check .
python -m compileall -q src
```
