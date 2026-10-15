# Operations

## Generated repository CI and image publication

The generated `Service CI` workflow runs on pull requests and pushes to `main`. It runs Ruff, `pip-audit`, and Helm lint. The chart-lint step supplies a synthetic digest calculated from `deploy/chart/Chart.yaml` because the chart intentionally rejects an empty digest; that fixture is only for linting.

The generated repository assumes `main` is its default branch for both image publication and the Argo CD Application's `targetRevision`. Change those settings together if the repository uses another default branch. Promotion and preview dispatch workflows check the repository's configured default branch dynamically.

On a push to `main`, after validation, the workflow builds and pushes `ghcr.io/{owner}/{repository}:sha-{commit}` with BuildKit provenance and SBOM enabled. It emits the resulting immutable digest in the GitHub Actions run summary and publishes an attestation. Deploy by digest, never by the commit tag.

For a private package, configure cluster-side GHCR pull access before deployment. The generated chart does not inject registry credentials into pods.

## Promote a digest through a pull request

1. In the generated repository's GitHub settings, create a `promotion` environment and require reviewer approval. Add `PROMOTION_TOKEN` as an environment secret. It must be a fine-grained token for a human account with repository contents and pull-request permissions. The token's account must be the same human who dispatches the workflow.
2. From the default branch, dispatch **Promote image digest** with the digest from the successful image publish run summary.
3. After environment approval, the workflow validates the digest, verifies the token's GitHub numeric account ID matches the human dispatcher, updates only `deploy/chart/values.yaml`, and opens a promotion PR using that human identity.
4. Review and merge the PR. Argo CD then observes the committed digest and reconciles the chart.

If the digest already matches chart values, the workflow reports that and creates no branch or PR. Do not place a bot author identity in the promotion commit.

## Deploy and remove a preview

1. Configure a dedicated Kubernetes credential as `KUBECONFIG_B64` in a `preview` GitHub environment. Require a reviewer before the job can access it. Prefer a dedicated, isolated cluster because namespace creation/deletion requires cluster-scoped namespace permissions.
2. From the default branch, dispatch **Preview** with `operation=deploy`, a positive numeric `pull_request_number`, and a published immutable `image_digest`.
3. The workflow derives the namespace; callers cannot select an arbitrary namespace. It verifies ownership metadata before using an existing namespace and waits for Helm readiness. A deployment failure may leave the namespace in place for diagnosis.
4. When finished, dispatch **Preview** again from the default branch with `operation=destroy` and the same PR number. No digest is needed for destruction. The workflow verifies ownership labels and repository annotation before uninstalling the release and deleting the namespace.

`launchpad preview-plan` and `launchpad destroy-plan` only print JSON descriptions. They do not contact Kubernetes. `launchpad render` only prints Helm YAML. The preview workflow is the only included direct, operator-dispatched cluster mutation path; Argo CD remains the GitOps reconciliation path for the main deployment.

If cleanup reports that ownership does not match, stop and inspect the namespace. Do not remove the ownership checks to force deletion. If a preview namespace was deleted outside Launchpad, the destroy workflow reports it as already absent.

## Local commands

Install the platform development extras, then create a project under an existing directory:

```bash
python -m pip install -e ".[dev]"
mkdir -p services
launchpad init payments-api --repository Raidensec/payments-api --output-parent ./services
launchpad check ./services/payments-api
```

With a real image digest copied from a publish run, render locally:

```bash
read -r -p "Published image digest (sha256:...): " IMAGE_DIGEST
launchpad render ./services/payments-api --digest "$IMAGE_DIGEST"
```

The CLI requires Helm 3.19 or later for `render`; the generated GitHub workflows install Helm 3.19.0. The CLI `preview-plan` and `destroy-plan` accept service/repository/PR inputs and never need credentials.

## What has not been validated here

No Kubernetes deployment, Argo CD sync, registry publish, image pull, GitHub environment approval, or AWS provisioning is performed by the platform's local checks. Those require the external accounts and cluster configuration described above. The platform CI performs Python lint/compile and generated chart validation; it does not claim to prove runtime cluster behavior.
