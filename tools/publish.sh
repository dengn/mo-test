#!/usr/bin/env bash
# Resume the already requested publication after GitHub credentials are ready.
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(gh api user --jq .login)" = dengn
if ! gh api repos/dengn/mo-test >/dev/null 2>&1; then
  gh repo create dengn/mo-test --private --description 'MatrixOne complete data science, complex analytics and deep ML case suites'
fi
existing=$(gh api repos/dengn/mo-test/branches/main --jq .commit.sha 2>/dev/null || true)
if [ -n "$existing" ] && [ "$existing" != "$(git rev-parse HEAD)" ]; then
  git -c credential.helper= -c 'credential.helper=!gh auth git-credential' fetch origin main
  if ! git merge-base --is-ancestor "$existing" HEAD; then
    echo 'Remote main is not an ancestor of local HEAD; refusing to overwrite.' >&2
    exit 1
  fi
fi
gh auth setup-git
git -c core.compression=0 -c pack.window=0 push origin main
test "$(gh api repos/dengn/mo-test/branches/main --jq .commit.sha)" = "$(git rev-parse HEAD)"
echo 'Verified: https://github.com/dengn/mo-test'
