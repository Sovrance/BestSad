# ADR 0008 — K0 v1.0.0 semantics: bounded integers, fuel, and total operations

**Status:** Accepted
**Date:** 2026-08-17
**Governs:** spec §8, §31.1 (K0 semantics require an ADR)

## Context

Spec §8.2 specifies `Int` as "mathematical integer in the reference semantics" and requires a
pure, deterministic, totally-trapping kernel with no ambient effects. Spec §8.3 prefers total
operations, with partial operations returning `Option` or an explicit `Trap`. Several details
that the spec leaves to the implementation nonetheless *are* semantics — they decide which
programs trap, so getting them wrong or changing them later silently invalidates comparisons.

Four such decisions had to be made to implement M1.

## Decision

**1. Integers are mathematical but bounded, with an explicit trap.**
`Int` is Python's arbitrary-precision integer, so no wraparound or overflow UB is inherited.
A magnitude bound of `2^64` is imposed, and exceeding it raises `VALUE_TOO_LARGE`. Unbounded
integers would let a short program (`mul` nested a few times) consume unbounded memory and
time, which breaks the determinism guarantee in practice — a program that OOMs is not
deterministic across machines. The bound is stated in the semantics rather than left to the
host, so the trap point is identical everywhere.

**2. Division and modulus truncate toward zero.**
Python's `//` floors; C-family languages truncate. Neither is "the" right answer, but the two
disagree on negative operands, and any later backend lowering must match the reference. Truncation
toward zero is chosen because it matches the LLVM/MLIR leg the compiler path (M12) will lower
to, so the translation validator has less to reconcile. `mod` takes the sign of the dividend,
consistently with truncated division.

**3. Fuel is charged proportional to work, not per node.**
The first implementation charged 1 unit per evaluated node. That made `range(0, 4096)` cost the
same as `add`, so fuel did not bound actual work. Fuel is now: 1 per operation, plus the size of
any list an operation constructs or traverses, plus the size of values compared structurally by
`eq`. This matters twice — fuel decides which programs trap (semantics), and search budgets are
metered in kernel steps (spec §26.4), so a mis-costed kernel would mis-report compute in exactly
the accounting that condition I depends on.

**4. `if` is the only non-strict operation; `and`/`or` are strict.**
Non-strict `if` is required: without it, `if x = 0 then 0 else 100/x` traps, and guarded
division is unwritable. Strictness elsewhere — including `and`/`or` — keeps the evaluation
order of every other operation trivially predictable. The cost is that `and(false, 1/0)` traps
where a short-circuiting language would return `false`. That is a real difference from most
human languages, so it is pinned by a test rather than left to be discovered.

## Consequences

- The trap set is closed at six kinds and is part of the kernel version hash.
- `LIST_LEN_LIMIT = 4096`, `DEFAULT_FUEL = 100_000`, `DEFAULT_DEPTH_LIMIT = 256`, and
  `INT_ABS_LIMIT = 2^64` are semantics. They are hashed into `KERNEL_VERSION_HASH` and pinned
  by `tests/kernel/test_frozen.py`.
- Any change to the above starts a new experiment lineage (spec §8.4). Fitness results across
  the change may not be compared.

## Residual

K0 has no recursion and no unbounded loop, so a fuel trap indicates a large or quadratic
program rather than a divergent one. Fuel is therefore a *resource* bound rather than a
halting device, and raising it changes which programs are solvable. The pre-registration
records the fuel value used, and it is part of the run manifest.
