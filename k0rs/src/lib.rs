//! `k0rs`: the Rust twin of the BestSad K0 v1.0.0 reference interpreter (BEST-VERIF-05).
//!
//! The Python reference in `src/bestsad/kernel/` is **normative** (ADR-0002). This crate is a
//! second implementation that must agree with it under the M1 differential sweep and that a
//! bounded model checker can say things about which no tool can say about the Python. If the
//! two ever disagree, the Python wins and this crate is fixed (ADR-0020).
//!
//! * `descriptor` -- the op table and the kernel version hash; `build.rs` refuses to build the
//!   crate unless the hash equals the Python constant.
//! * `interp` -- the evaluator, transcribed line by line from `interpreter.py`.
//! * `wire` -- the JSON line protocol `bestsad.verify.twin` drives for the differential sweep.
//! * `proofs` -- Kani harnesses (`cargo kani`), compiled only under `cfg(kani)`.

pub mod descriptor;
pub mod interp;
pub mod term;
pub mod value;
pub mod wire;

#[cfg(kani)]
mod proofs;

pub use descriptor::{
    canonical_descriptor, kernel_version_hash, DEFAULT_DEPTH_LIMIT, DEFAULT_FUEL, INT_ABS_LIMIT,
    KERNEL_VERSION, LIST_LEN_LIMIT, PYTHON_KERNEL_VERSION_HASH,
};
pub use interp::{Execution, Kernel, Outcome, State, TrapKind};
pub use term::{IntLit, Op, Program, Term};
pub use value::{value_cost, value_equal, Closure, Env, Value};
