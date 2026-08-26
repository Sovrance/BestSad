"""`scripts/ci_local.py` must not drift out of sync with `.github/workflows/ci.yml` (ADR 0018).

With no runners, the local script is the only thing that actually executes the gates. If a job
is added to `ci.yml` and not to the script, that gate silently stops being run by anything at
all — and unlike a CI outage, nothing goes red to say so. This test is what makes that
impossible to do quietly.

It lives in `tests/integrity` for the same reason the trust-boundary tests do: it protects a
control rather than a behaviour.
"""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
LOCAL_RUNNER = REPO_ROOT / "scripts" / "ci_local.py"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _runner_text() -> str:
    return LOCAL_RUNNER.read_text(encoding="utf-8")


def _ci_job_names() -> list[str]:
    return re.findall(r"^\s{4}name:\s*(.+?)\s*$", _workflow_text(), re.M)


def _ci_pytest_invocations() -> list[str]:
    return sorted(set(re.findall(r"run: (pytest [^\n]+)", _workflow_text())))


def _local_pytest_arg_sets() -> list[list[str]]:
    gates = re.findall(r'\[sys\.executable, "-m", "pytest"([^\]]*)\]', _runner_text())
    return [re.findall(r'"([^"]+)"', g) for g in gates]


class BothFilesExist(unittest.TestCase):
    def test_the_workflow_is_still_present(self):
        """ADR 0018 keeps ci.yml deliberately: it is the description the local runner mirrors,
        and it works again unchanged if runners return."""
        self.assertTrue(WORKFLOW.exists(), "ci.yml was removed; ADR 0018 says it stays")

    def test_the_local_runner_is_present_and_executable(self):
        self.assertTrue(LOCAL_RUNNER.exists())


class LocalRunnerMirrorsCI(unittest.TestCase):
    def test_every_ci_job_name_appears_in_the_local_runner(self):
        missing = [n for n in _ci_job_names() if n not in _runner_text()]
        self.assertEqual(
            missing, [], f"ci.yml jobs with no local gate: {missing}"
        )

    def test_the_workflow_still_defines_the_jobs_we_expect(self):
        """Guards the guard: if the name regex stops matching, the test above passes
        vacuously against an empty list."""
        names = _ci_job_names()
        self.assertGreaterEqual(len(names), 6, f"parsed only {names} from ci.yml")
        self.assertIn("tests", names)
        self.assertIn("evaluator integrity (Gate G1)", names)
        self.assertIn("K0 differential sweep (Gate G0)", names)

    def test_every_ci_pytest_invocation_is_mirrored_exactly(self):
        invocations = _ci_pytest_invocations()
        self.assertGreaterEqual(len(invocations), 5, f"parsed only {invocations}")
        local = _local_pytest_arg_sets()
        for invocation in invocations:
            want = shlex.split(invocation)[1:]  # drop the leading "pytest"
            with self.subTest(invocation=invocation):
                self.assertIn(
                    want,
                    local,
                    f"ci.yml runs `{invocation}` but no local gate runs those arguments",
                )

    def test_an_unavailable_gate_is_never_reported_as_passing(self):
        """The distinction ADR 0018 turns on. UNAVAILABLE must be its own status and must not
        collapse into the OK path."""
        source = _runner_text()
        self.assertIn("UNAVAILABLE", source)
        self.assertIn("INCOMPLETE", source)
        # The OK line must be guarded by there being no unavailable gates.
        self.assertRegex(
            source,
            r"if unavailable:[\s\S]{0,600}?INCOMPLETE",
            "the unavailable branch must report INCOMPLETE before any OK result",
        )

    def test_every_docker_command_in_the_workflow_is_mirrored(self):
        """The gap a name-only mirror test misses.

        The first version of the local gate ran `docker build` and nothing else, so it would
        have reported PASS having verified that the image assembles and none of what the job
        actually asserts: no hidden assets, uid 10001, and a read-only start with no network
        and no capabilities. Matching job *names* did not catch that, because the name matched
        perfectly. Matching the commands does.
        """
        script = (REPO_ROOT / "scripts" / "evaluator_image_gate.sh").read_text(encoding="utf-8")
        workflow = _workflow_text()

        # The distinguishing fragment of each `docker` invocation in the evaluator-image job.
        required = [
            "docker build -f src/bestsad/evaluator/Dockerfile",
            'name "hidden_evaluator*"',          # the hidden-asset search
            "canonicalize.py",                   # its positive control
            "--entrypoint id bestsad-evaluator:ci -u",  # the uid check
            "--network none",
            "--read-only",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
        ]
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, workflow, "fragment is not in ci.yml; update this test")
                self.assertIn(
                    fragment,
                    script,
                    f"ci.yml asserts {fragment!r} but the local gate never does",
                )

    def test_the_image_gate_checks_more_than_the_build(self):
        script = (REPO_ROOT / "scripts" / "evaluator_image_gate.sh").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            script.count("docker run"), 3,
            "the image gate must run the built image, not merely build it",
        )
        self.assertIn("set -euo pipefail", script, "a failing step must fail the gate")

    def test_tooling_is_probed_for_usability_not_mere_presence(self):
        """`which(docker)` succeeds on a machine whose daemon is down, which turned a gate
        that could not run into a gate that appeared to fail."""
        source = _runner_text()
        self.assertIn("probe", source)
        self.assertIn('["docker", "info"]', source)


if __name__ == "__main__":
    unittest.main()
