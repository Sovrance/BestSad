"""The Z3 adapter: probe, determinism, resource accounting, and the counterexample discipline.

Three things this module promises and the tests hold it to:

1. **Absence is loud, not fatal.** `probe()` is True only if `z3` imports *and* solves a trivial
   query. Otherwise every entry point returns `unknown` with reason `solver_unavailable`, and
   no exception escapes (ADR-0019, the ADR-0018 pattern).
2. **Every counterexample is re-executed on the reference.** A `sat` model is converted to K0
   values and both programs are run on `kernel/interpreter.py`. The predicted outcome on each
   side must match the reference's, and the two must disagree. If not, the adapter raises
   `EncoderDivergence` rather than reporting anything -- this is the single most important
   check in the plane, because it is how the encoder is kept honest against the anchor.
3. **Solver time is compute.** Wall and CPU seconds and a call counter are charged to the
   compute ledger (spec §26.4) when one is supplied, alongside any kernel steps the
   re-execution spent.

Determinism: Z3 is constructed with fixed seeds (`sat.random_seed=0`, `smt.random_seed=0`), so
the *verdict* is deterministic given the query and the solver version, which the analyzer
result records. Solver *timing* is not deterministic, and it is stored in the same record, so
the record's content id varies between runs; only the verdict is compared across runs.
"""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from ...bsir.equivalence import (
    SYMBOLIC_OBLIGATION,
    EquivalenceContract,
    EquivalenceResult,
    _charge as _charge_kernel,
)
from ...kernel.interpreter import ExecutionResult, Kernel
from ...kernel.terms import Program
from ...kernel.traps import Trap, TrapKind, TrapSignal
from ...kernel.typecheck import TypeError_, typecheck
from ...kernel.values import render
from ...sre.ids import as_content_id
from ...sre.objects import AnalyzerResult, Counterexample, Fact, Producer
from .bounds import SolverScope
from .encode import OBSERVABLE, Encoder, Outcome, Unsupported

ANALYZER_ID = "bestsad.verify.smt"
ANALYZER_VERSION = "0.1.0"

#: Reason recorded when no usable solver is present.
SOLVER_UNAVAILABLE = "solver_unavailable"

#: Traps the encoding does not model (ADR-0019). A witness on which the reference produces one
#: of these lies outside the verdict's assumptions and is reported as UNKNOWN, not as a bug.
EXCLUDED_TRAPS: frozenset[TrapKind] = frozenset({TrapKind.FUEL_EXHAUSTED, TrapKind.DEPTH_EXCEEDED})

Status = Literal["equiv", "non_equiv", "unknown"]


class SolverUnavailable(RuntimeError):
    """Z3 cannot be imported or cannot solve. Raised only by helpers that have no UNKNOWN to
    return; the tier entry points catch it and report."""


class EncoderDivergence(AssertionError):
    """The encoder and the reference interpreter disagree on a concrete input.

    Deliberately an error, never a verdict: a symbolic tier that has been caught lying about K0
    must not be allowed to say anything until it is fixed. The reference wins (ADR-0002).
    """


@dataclass(frozen=True, slots=True)
class SymbolicResult:
    """What one solver call established, and what it cost."""

    status: Status
    model: dict[str, Any] | None
    assumptions: tuple[str, ...]
    scope: dict[str, Any]
    analyzer_result_id: str
    wall_s: float
    cpu_s: float
    reason: str = ""
    solver_version: str = ""
    verification_coverage: float = 0.0
    coverage_basis: str = ""
    kernel_steps: int = 0
    #: 1 when Z3 was actually invoked; 0 when the attempt ended before reaching it.
    solver_calls: int = 0
    witness: tuple[Any, ...] | None = None
    left_outcome: ExecutionResult | None = None
    right_outcome: ExecutionResult | None = None
    analyzer_result: dict[str, Any] = field(default_factory=dict)
    fact: dict[str, Any] = field(default_factory=dict)
    counterexample: Counterexample | None = None

    def verification_score(self, *, left_root: str, right_root: str, verdict: str) -> dict[str, Any]:
        """The spec §19.1 record: coverage and cost, stated, per claim
        (`schemas/verification_score.schema.json`)."""
        return {
            "verification_score_version": "0.1",
            "subject": {"left": as_content_id(left_root), "right": as_content_id(right_root)},
            "verdict": verdict,
            "verification_coverage": self.verification_coverage,
            "coverage_basis": self.coverage_basis,
            "verification_cost": {
                "solver_wall_s": self.wall_s,
                "solver_cpu_s": self.cpu_s,
                "solver_calls": self.solver_calls,
                "kernel_steps": self.kernel_steps,
            },
            "scope": dict(self.scope),
            "assumptions": list(self.assumptions),
            "analyzer_result_ref": self.analyzer_result_id,
            "producer": {"id": ANALYZER_ID, "version": self.solver_version or ANALYZER_VERSION},
        }


# -- the solver -------------------------------------------------------------------------------


def _import_z3() -> Any | None:
    try:
        return importlib.import_module("z3")
    except ImportError:
        return None


def probe() -> bool:
    """True only if `z3` imports **and** solves a trivial query.

    Importability alone is the `shutil.which("docker")` mistake ADR-0018 records: a module on
    the path whose native library is broken would make a gate look present while nothing runs.
    """
    z3 = _import_z3()
    if z3 is None:
        return False
    try:
        solver = z3.Solver()
        x = z3.Int("probe")
        solver.add(x > 0, x < 2)
        return solver.check() == z3.sat and solver.model().eval(x).as_long() == 1
    except Exception:  # pragma: no cover - a broken native library
        return False


def _solver(z3: Any, timeout_ms: int) -> Any:
    z3.set_param("sat.random_seed", 0)
    z3.set_param("smt.random_seed", 0)
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))
    solver.set("random_seed", 0)
    return solver


def _version(z3: Any) -> str:
    return f"z3-{z3.get_version_string()}"


def _prepare(
    z3: Any, scope: SolverScope, programs: Sequence[Program], kernel: Kernel
) -> tuple[Encoder, dict[str, tuple[Any, Any]], list[Outcome]]:
    """Typecheck, expand primitives, and encode `programs` over one shared set of inputs."""
    expanded = []
    for program in programs:
        typecheck(program)
        body = kernel.expand(program.body)
        expanded.append(Program(program.params, body, program.result_type))
    encoder = Encoder(scope, z3)
    env = encoder.inputs(programs[0].params)
    outcomes = [encoder.program(p, env) for p in expanded]
    return encoder, env, outcomes


class SymbolicExecutor:
    """Evaluate one program on many concrete inputs *through the encoding*.

    The program is encoded once; each call pins the inputs under a solver push/pop and solves
    for the output. `run` returns `None` when the inputs lie outside the bounded domain (a list
    longer than `N`, an intermediate that would exceed it). This is the differential test's
    instrument; the equivalence path does not go through here.
    """

    def __init__(self, program: Program, scope: SolverScope | None = None, *,
                 kernel: Kernel | None = None) -> None:
        z3 = _import_z3()
        if z3 is None or not probe():
            raise SolverUnavailable(SOLVER_UNAVAILABLE)
        self.z3 = z3
        self.program = program
        self.scope = scope or SolverScope()
        k = kernel if kernel is not None else Kernel()
        self.encoder, self.env, (self.outcome,) = _prepare(z3, self.scope, [program], k)
        self.solver = _solver(z3, self.scope.timeout_ms)
        self.solver.add(*self.encoder.constraints)

    def run(self, inputs: Sequence[Any]) -> ExecutionResult | None:
        z3, solver = self.z3, self.solver
        pins: list[Any] = []
        for (name, ty), value in zip(self.program.params, inputs):
            pinned = self.encoder.pin(self.env[name][0], value, ty)
            if pinned is None:
                return None
            pins.extend(pinned)
        solver.push()
        try:
            solver.add(*pins)
            verdict = solver.check()
            if verdict == z3.unsat:
                return None
            if verdict != z3.sat:
                raise SolverUnavailable(f"solver returned {verdict}: {solver.reason_unknown()}")
            trap, value = self.encoder.read_outcome(solver.model(), self.outcome)
        finally:
            solver.pop()
        return ExecutionResult(value=value, trap=trap, trace_hash="symbolic")


def symbolic_execute(
    program: Program,
    inputs: Sequence[Any],
    scope: SolverScope | None = None,
    *,
    kernel: Kernel | None = None,
) -> ExecutionResult | None:
    """One-shot form of `SymbolicExecutor`: encode, pin, solve for the output."""
    return SymbolicExecutor(program, scope, kernel=kernel).run(inputs)


def check_equivalence(
    left: Program,
    right: Program,
    contract: EquivalenceContract,
    *,
    kernel: Kernel | None = None,
    ledger: Any | None = None,
    timeout_ms: int | None = None,
) -> SymbolicResult:
    """Decide `left ≡ right` over the contract's bounded domain (design §2.4).

    `equiv` is returned only when the solver says `unsat` for the negated equivalence. `sat`
    goes through the counterexample discipline before it may be called `non_equiv`. Everything
    else -- no solver, unsupported feature, ill-typed program, timeout, a witness the
    assumptions exclude -- is `unknown` with the reason recorded.
    """
    wall0, cpu0 = time.perf_counter(), time.process_time()
    k = kernel if kernel is not None else Kernel()

    def finish(status: Status, *, reason: str = "", **extra: Any) -> SymbolicResult:
        wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
        return _finish(status, reason=reason, wall=wall, cpu=cpu, contract=contract,
                       left=left, right=right, kernel=k, ledger=ledger, **extra)

    z3 = _import_z3()
    if z3 is None or not probe():
        return finish("unknown", reason=SOLVER_UNAVAILABLE)

    try:
        scope = SolverScope.parse(contract.solver_scope)
    except ValueError as exc:
        return finish("unknown", reason=f"invalid solver_scope: {exc}")
    if timeout_ms is not None:
        scope = SolverScope(scope.list_bound, scope.int_abs_limit, timeout_ms, scope.unroll_depth)
    if contract.observable_contract_ref != OBSERVABLE:
        return finish("unknown", scope=scope,
                      reason=f"unsupported observable {contract.observable_contract_ref!r}")
    if left.params != right.params:
        return finish("unknown", scope=scope, reason="parameter lists differ; no shared input domain")

    try:
        encoder, env, (lo, ro) = _prepare(z3, scope, [left, right], k)
        same = encoder.same_outcome(lo, ro)
    except TypeError_ as exc:
        return finish("unknown", scope=scope, reason=f"ill-typed program: {exc}")
    except TrapSignal as exc:
        return finish("unknown", scope=scope, reason=f"cannot expand primitives: {exc}")
    except Unsupported as exc:
        return finish("unknown", scope=scope, reason=str(exc))

    coverage, basis = scope.coverage(
        (t for _, t in left.params), list_bound_applied=encoder.list_bound_applied
    )
    solver = _solver(z3, scope.timeout_ms)
    solver.add(*encoder.constraints)
    solver.add(z3.Not(same))
    smt2 = solver.to_smt2()
    verdict = solver.check()
    common = dict(scope=scope, encoder=encoder, smt2=smt2, solver_version=_version(z3),
                  coverage=coverage, basis=basis, solver_ran=True)

    if verdict == z3.unsat:
        return finish("equiv", **common)

    if verdict != z3.sat:
        return finish("unknown", reason=f"solver returned unknown: {solver.reason_unknown()}",
                      **common)

    # -- counterexample discipline --
    model = solver.model()
    try:
        witness = tuple(encoder.concretize(model, env[name][0], ty) for name, ty in left.params)
        predicted = [encoder.read_outcome(model, o) for o in (lo, ro)]
    except Unsupported as exc:
        return finish("unknown", reason=f"model could not be read back: {exc}", **common)

    actual = [k.execute(p, witness, fuel=contract.max_steps) for p in (left, right)]
    steps = sum(r.fuel_used for r in actual)
    executions = 2
    excluded = [r for r in actual if r.trap is not None and r.trap.kind in EXCLUDED_TRAPS]
    if excluded:
        return finish(
            "unknown",
            reason=("witness lies outside the assumptions: the reference traps "
                    + ", ".join(sorted({r.trap.kind.value for r in excluded}))),
            witness=witness, kernel_steps=steps, executions=executions, **common,
        )
    for side, (trap, value), ref in zip(("left", "right"), predicted, actual):
        agree = (trap is not None and ref.trap is not None and trap.kind is ref.trap.kind) or (
            trap is None and ref.trap is None and ExecutionResult(value=value).same_outcome(ref)
        )
        if not agree:
            raise EncoderDivergence(
                f"encoder and reference disagree on the {side} program at inputs "
                f"{[render(v) for v in witness]}: encoder predicted "
                f"{trap if trap is not None else render(value)}, reference produced {ref}. "
                "The reference is normative (ADR-0002); fix the encoder."
            )
    if actual[0].same_outcome(actual[1]):
        raise EncoderDivergence(
            f"solver produced a witness {[render(v) for v in witness]} on which the reference "
            f"agrees ({actual[0]}); the encoder's notion of equality diverges from K0's"
        )
    return finish("non_equiv", witness=witness, actual=actual, kernel_steps=steps,
                  executions=executions, **common)


def _outcome_wire(result: ExecutionResult) -> dict[str, Any]:
    if result.trap is not None:
        return {"trap": result.trap.kind.value}
    return {"value": render(result.value)}


def _finish(
    status: Status,
    *,
    reason: str,
    wall: float,
    cpu: float,
    contract: EquivalenceContract,
    left: Program,
    right: Program,
    kernel: Kernel,
    ledger: Any | None,
    scope: SolverScope | None = None,
    encoder: Encoder | None = None,
    smt2: str = "",
    solver_version: str = "",
    coverage: float = 0.0,
    basis: str = "",
    witness: tuple[Any, ...] | None = None,
    actual: Sequence[ExecutionResult] | None = None,
    kernel_steps: int = 0,
    executions: int = 0,
    solver_ran: bool = False,
) -> SymbolicResult:
    """Assemble the result, the analyzer-result record, and the ledger charge for every exit."""
    from ...bsir.canonicalize import semantic_hash

    scope_dict = scope.to_dict() if scope is not None else {}
    assumptions = scope.assumptions() if scope is not None else ()

    def program_id(program: Program) -> str:
        try:
            return as_content_id(semantic_hash(program, kernel))
        except TrapSignal:
            # A primitive the kernel cannot expand: hash the unexpanded term so the record
            # still names its inputs. The verdict in that case is UNKNOWN anyway.
            return as_content_id(semantic_hash(program))

    left_id, right_id = program_id(left), program_id(right)

    fact_status = {"equiv": "SUPPORTED", "non_equiv": "CONTRADICTED", "unknown": "UNKNOWN"}[status]
    producer = Producer(ANALYZER_ID, f"{ANALYZER_VERSION}+{solver_version or 'no-solver'}")
    fact = Fact(
        predicate="symbolic_equivalence",
        status=fact_status,
        producer=producer,
        inputs=(left_id, right_id),
        assumptions=assumptions,
        detail={"scope": scope_dict, "reason": reason} if reason else {"scope": scope_dict},
    )
    coverage_record: dict[str, Any] = {
        "status": status,
        "observable": contract.observable_contract_ref,
        "scope": scope_dict,
        "assumptions": list(assumptions),
        "verificationCoverage": coverage,
        "coverageBasis": basis,
        "solverVersion": solver_version,
        "smtlib2": smt2,
        "wallSeconds": wall,
        "cpuSeconds": cpu,
        "domainConstraints": len(encoder.constraints) if encoder is not None else 0,
        "listBoundApplied": bool(encoder.list_bound_applied) if encoder is not None else False,
    }
    unresolved = ()
    if status == "unknown":
        unresolved = ({"obligation": SYMBOLIC_OBLIGATION, "reason": reason},)
    analyzer = AnalyzerResult(
        producer=producer,
        inputs=(left_id, right_id),
        facts=(fact.id,),
        coverage=coverage_record,
        unresolved=unresolved,
    )
    analyzer_wire = analyzer.to_wire()

    counterexample = None
    model = None
    if status == "non_equiv" and witness is not None and actual is not None:
        kind = "DIVERGENT_TRAP" if any(r.trap is not None for r in actual) else "DIVERGENT_RESULT"
        counterexample = Counterexample(
            kind=kind,
            witness={"inputs": [repr(v) for v in witness]},
            left_outcome=_outcome_wire(actual[0]),
            right_outcome=_outcome_wire(actual[1]),
            evidence_refs=(analyzer_wire["id"],),
            detail={"source": "smt-model", "reExecutedOnReference": True},
        )
        model = {name: render(v) for (name, _), v in zip(left.params, witness)}

    _charge(ledger, wall_s=wall, cpu_s=cpu, kernel_steps=kernel_steps, executions=executions,
            solver_ran=solver_ran)

    return SymbolicResult(
        status=status,
        model=model,
        assumptions=assumptions,
        scope=scope_dict,
        analyzer_result_id=analyzer_wire["id"],
        wall_s=wall,
        cpu_s=cpu,
        reason=reason,
        solver_version=solver_version,
        verification_coverage=coverage,
        coverage_basis=basis,
        kernel_steps=kernel_steps,
        solver_calls=1 if solver_ran else 0,
        witness=witness,
        left_outcome=actual[0] if actual else None,
        right_outcome=actual[1] if actual else None,
        analyzer_result=analyzer_wire,
        fact=fact.to_wire(),
        counterexample=counterexample,
    )


def _charge(ledger: Any | None, *, wall_s: float, cpu_s: float, kernel_steps: int,
            executions: int, solver_ran: bool) -> None:
    """Charge the tier's time, and any re-execution, to the compute ledger (spec §26.4).

    Time is charged on every exit -- an attempt that ended in UNKNOWN still spent it -- while
    `solver_calls` counts only invocations that reached Z3. Kernel steps go through the same
    `_charge` path `bsir/equivalence.py` uses for the dynamic tier, so a witness re-execution
    and a sampling pass are metered identically.
    """
    if ledger is None:
        return
    ledger.add(solver_calls=1 if solver_ran else 0, solver_wall_s=wall_s, solver_cpu_s=cpu_s,
               verifier_time_s=wall_s)
    if executions:
        _charge_kernel(ledger, kernel_steps, executions)


# -- Tier 2 as `bsir/equivalence.py` sees it ----------------------------------------------------


def symbolic_tier(
    left: Program,
    right: Program,
    contract: EquivalenceContract,
    *,
    left_root: str,
    right_root: str,
    kernel: Kernel | None = None,
    ledger: Any | None = None,
) -> EquivalenceResult:
    """The `require_proof` branch of `equivalent()`: map a solver result onto the verdict set.

    `EQUIV_SYMBOLIC` only on `equiv`; `NON_EQUIV` with the re-executed witness on `non_equiv`;
    `UNKNOWN` with the obligation left open otherwise. The dynamic tier is never used as a
    fallback here -- the caller asked for a proof.
    """
    result = check_equivalence(left, right, contract, kernel=kernel, ledger=ledger)

    def build(verdict: str, **kw: Any) -> EquivalenceResult:
        return EquivalenceResult(left_root, right_root, verdict, contract, **kw)

    score = result.verification_score(left_root=left_root, right_root=right_root, verdict={
        "equiv": "EQUIV_SYMBOLIC", "non_equiv": "NON_EQUIV", "unknown": "UNKNOWN",
    }[result.status])
    base_detail = {
        "solver": result.solver_version,
        "scope": dict(result.scope),
        "verification_score": score,
        "kernel_steps": result.kernel_steps,
    }

    if result.status == "equiv":
        return build(
            "EQUIV_SYMBOLIC",
            assumptions=result.assumptions,
            evidence_refs=(result.analyzer_result_id,),
            detail={
                **base_detail,
                "basis": "solver returned unsat for the negated equivalence over the declared "
                         "bounded domain; a bounded proof under the listed assumptions",
            },
        )
    if result.status == "non_equiv":
        return build(
            "NON_EQUIV",
            evidence_refs=(result.analyzer_result_id,),
            counterexample=result.counterexample,
            detail={
                **base_detail,
                "cases": 1,
                "basis": "solver model, re-executed on the K0 reference interpreter",
            },
        )
    return build(
        "UNKNOWN",
        unresolved=(SYMBOLIC_OBLIGATION,),
        evidence_refs=(result.analyzer_result_id,),
        detail={**base_detail, "reason": result.reason},
    )
