#!/usr/bin/env bash
# Create a release tag only after the complete CI workflow succeeded for HEAD.
#
# Preparation order (all changes are committed before invoking this script):
#   1. bump plugin.yaml/pyproject.toml and both changelogs;
#   2. push main and wait for the CI run for that exact commit to succeed;
#   3. run: GITEA_TOKEN=... ./scripts/release.sh vX.Y.Z <ci-run-id>.
#
# The script deliberately does not generate or commit changelogs: doing so after
# CI would make the tag point at a commit that CI did not test.
set -euo pipefail

if [[ $# -ne 2 || ! "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$ ]]; then
  echo "Usage: GITEA_TOKEN=... $0 vX.Y.Z <successful-ci-run-id>" >&2
  exit 1
fi

VERSION="$1"
CI_RUN_ID="$2"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
  echo "ERROR: releases can only be tagged from main." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is not clean." >&2
  exit 1
fi
: "${GITEA_TOKEN:?Set GITEA_TOKEN to a token that can read Actions runs and create tags.}"

git fetch --quiet gitea main --tags
HEAD_SHA="$(git rev-parse HEAD)"
REMOTE_MAIN_SHA="$(git rev-parse gitea/main)"
if [[ "$HEAD_SHA" != "$REMOTE_MAIN_SHA" ]]; then
  echo "ERROR: local main ($HEAD_SHA) is not the current gitea/main ($REMOTE_MAIN_SHA)." >&2
  exit 1
fi

TAG_VERSION="${VERSION#v}"
PLUGIN_VERSION="$(awk '/^version:/ {print $2; exit}' plugin.yaml)"
if [[ "$PLUGIN_VERSION" != "$TAG_VERSION" ]]; then
  echo "ERROR: plugin.yaml version ($PLUGIN_VERSION) does not match $VERSION." >&2
  exit 1
fi

# These checks validate that the committed release notes and configuration
# describe this exact release candidate. The remote CI check below remains the
# authority for the complete matrix, security scan, and dependency audits.
python scripts/check-doc-claims.py
python scripts/check-config-reference.py
python scripts/check-ru-en-parity.py

REMOTE_URL="$(git remote get-url gitea)"
if [[ "$REMOTE_URL" =~ ^https://([^/]+)/([^/]+)/([^/.]+)(\.git)?$ ]]; then
  GITEA_HOST="${BASH_REMATCH[1]}"
  REPO_OWNER="${BASH_REMATCH[2]}"
  REPO_NAME="${BASH_REMATCH[3]}"
else
  echo "ERROR: unsupported gitea remote URL: $REMOTE_URL" >&2
  exit 1
fi
API_BASE="https://$GITEA_HOST/api/v1/repos/$REPO_OWNER/$REPO_NAME"
AUTH_HEADER="Authorization: token $GITEA_TOKEN"

RUN_JSON="$(curl --fail --silent --show-error -H "$AUTH_HEADER" "$API_BASE/actions/runs/$CI_RUN_ID")"
JOBS_JSON="$(curl --fail --silent --show-error -H "$AUTH_HEADER" "$API_BASE/actions/runs/$CI_RUN_ID/jobs?limit=100")"

python - "$HEAD_SHA" "$CI_RUN_ID" <<'PY' <<<"$RUN_JSON"$'\n'"$JOBS_JSON"
import json
import sys

expected_sha, run_id = sys.argv[1:]
run = json.loads(sys.stdin.readline())
jobs_response = json.loads(sys.stdin.readline())
run_sha = run.get("head_sha") or run.get("head_commit", {}).get("id")
if run.get("status") != "success" or run_sha != expected_sha:
    raise SystemExit(
        f"CI run {run_id} is not successful for HEAD: status={run.get('status')!r}, "
        f"head_sha={run_sha!r}, expected={expected_sha!r}"
    )

jobs = jobs_response.get("jobs", jobs_response if isinstance(jobs_response, list) else [])
if not jobs:
    raise SystemExit(f"CI run {run_id} returned no jobs; refusing to tag.")
required = ("test", "test-current-core", "security", "dependency-audit")
names = [job.get("name", "") for job in jobs]
missing = [name for name in required if not any(job_name == name or job_name.startswith(name + " ") for job_name in names)]
failed = [job.get("name", "<unnamed>") for job in jobs if job.get("status") != "success"]
if missing or failed:
    raise SystemExit(
        f"CI run {run_id} is incomplete or unsuccessful: missing={missing}, failed={failed}"
    )
PY

if git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
  echo "ERROR: tag $VERSION already exists locally." >&2
  exit 1
fi
if git ls-remote --exit-code --tags gitea "refs/tags/$VERSION" >/dev/null 2>&1; then
  echo "ERROR: tag $VERSION already exists on gitea." >&2
  exit 1
fi

git tag -a "$VERSION" -m "Release $VERSION" "$HEAD_SHA"
git push gitea "$VERSION"
echo "Release tag $VERSION published for verified commit $HEAD_SHA."
