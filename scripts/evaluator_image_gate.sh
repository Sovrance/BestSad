#!/usr/bin/env bash
# The evaluator-image job from .github/workflows/ci.yml, as a script (ADR 0018).
#
# All four steps, not just the build. The build proves the image assembles; the value of this
# gate is entirely in the three checks after it -- what the image does not contain, and what it
# cannot do. A local gate that ran only `docker build` and reported PASS would say "the
# evaluator boundary holds" having tested none of it, which is the failure ADR 0018 is written
# against.
#
# Kept byte-for-byte faithful to the workflow's commands, including the probe's positive
# control. tests/integrity/test_local_gates_mirror_ci.py fails if the two drift.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "--- build ---"
docker build -f src/bestsad/evaluator/Dockerfile -t bestsad-evaluator:ci .

echo "--- image carries no hidden evaluation assets (spec §27.2) ---"
# The query carries its own positive control. `canonicalize.py` is known to be in the image,
# so if the search cannot find the file that is definitely there, its silence about the files
# that must not be there proves nothing.
probe="$(docker run --rm --user 0 --entrypoint sh bestsad-evaluator:ci \
           -c 'find / -xdev \( -name "hidden_evaluator*" -o -name "canonicalize.py" \) -print' \
         || true)"
if ! printf '%s\n' "$probe" | grep -q 'canonicalize\.py'; then
  echo "ERROR: the image probe missed its own positive control; the search did not run" >&2
  exit 1
fi
if printf '%s\n' "$probe" | grep -q 'hidden_evaluator'; then
  echo "ERROR: hidden evaluation assets are present in the evaluator image:" >&2
  printf '%s\n' "$probe" | grep 'hidden_evaluator' >&2
  exit 1
fi
echo "ok: positive control found, no hidden evaluation assets"

echo "--- runs unprivileged ---"
uid="$(docker run --rm --entrypoint id bestsad-evaluator:ci -u)"
test "$uid" = "10001" || { echo "ERROR: image runs as uid $uid" >&2; exit 1; }
echo "ok: uid 10001"

echo "--- starts read-only, with no network and no capabilities ---"
docker run --rm \
  --network none \
  --read-only \
  --tmpfs /scratch:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  bestsad-evaluator:ci --help
echo "ok: starts under the full restriction set"
