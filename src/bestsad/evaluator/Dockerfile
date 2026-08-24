# Evaluator image — the deployment half of spec §27.1 (ADR-0005).
#
# `isolation.py` supplies what a Python process can enforce about itself: rlimits, a cleared
# environment, a scratch working directory, and the audit hook. Three things in §27.1 are not
# expressible from inside the process, and this image is where they live:
#
#   * a read-only base filesystem with a writable ephemeral scratch mount;
#   * no network namespace at all, rather than a hook that denies socket calls;
#   * an unprivileged, non-root user with no host credentials reachable.
#
# The image deliberately does **not** contain `hidden_evaluator/`. Spec §27.2 requires the
# evaluator to run outside the candidate-controlled namespace, and ADR-0003 records the residual
# that the assets currently share a checkout. Baking them into the image would make that residual
# permanent and shippable; mounting them read-only at run time keeps the separation real.
#
# Build from the repository root:
#
#     docker build -f src/bestsad/evaluator/Dockerfile -t bestsad-evaluator:dev .
#
# Run with the properties this file cannot assert on its own — they are `docker run` flags, and
# omitting them silently discards most of the isolation:
#
#     docker run --rm \
#       --network none \
#       --read-only \
#       --tmpfs /scratch:rw,noexec,nosuid,size=256m \
#       --cap-drop ALL \
#       --security-opt no-new-privileges \
#       --pids-limit 128 \
#       --memory 1g --cpus 1 \
#       -v "$PWD/hidden_evaluator:/hidden:ro" \
#       bestsad-evaluator:dev bestsad --help
#
# A seccomp profile is the one §27.1 item still outstanding after this file: Docker's default
# profile applies, but the program has not declared a syscall allowlist of its own. ADR-0005
# tracks it.

FROM python:3.11-slim AS build

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip wheel --no-cache-dir --no-deps -w /wheels .

FROM python:3.11-slim

# No compilers, no package manager credentials, no shell history: the runtime stage copies a
# built wheel rather than the source tree, so nothing that built the image is reachable from
# inside it.
COPY --from=build /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
 && rm -rf /wheels \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin evaluator

# Scratch is a mount point, not a directory in the image. With `--read-only` and the tmpfs flag
# above it is the only writable path; without them the container starts and this comment is the
# only thing that says the isolation was lost, which is why the run command above is part of the
# contract rather than a suggestion.
RUN mkdir -p /scratch && chown evaluator:evaluator /scratch

USER evaluator
WORKDIR /scratch

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    BESTSAD_SCRATCH=/scratch \
    BESTSAD_HIDDEN_ROOT=/hidden

# PYTHONHASHSEED is pinned because M1's acceptance test requires determinism across processes
# under varying hash seeds; the image fixes it so a container run is reproducible by default.

ENTRYPOINT ["bestsad"]
CMD ["--help"]
