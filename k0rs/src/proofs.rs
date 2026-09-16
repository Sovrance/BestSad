//! Kani proof harnesses for the K0 twin (BEST-VERIF-05, ADR-0020).
//!
//! What these prove, and only this: for every input within the stated bounds, the named
//! function returns `Value | Trap(kind)` without panicking, and the K0 bounds and the ADR-0008
//! cost model hold. Every harness is bounded -- `kani::any()` over a bounded representation and
//! `kani::unwind(N)` on loops -- and the bound is stated on the harness. Agreement with the
//! Python reference is **not** a Kani property; that is the differential sweep in
//! `tests/verify/test_k0_twin.py`. Aliasing, provenance and concurrency are not checked here.
//!
//! Run with `cargo kani` from `k0rs/` (or `scripts/kani_gate.py`, which holds every harness to
//! the 60 s budget). A harness that exceeds the budget is split, never loosened.
//!
//! What is *not* here, and why (ADR-0020, amendment of 2026-09-16): harnesses that reach
//! `Kernel::eval` or `apply_first_order` -- even `add(1, 2)` on concrete inputs -- exceed the
//! budget by more than an order of magnitude, because CBMC unwinds the evaluator's recursion at
//! every call site and models every `Vec<Value>` and `Box<Value>` on a symbolic heap. So did
//! every statement of "div truncates toward zero" that relates the quotient back to the
//! operands (it needs a second 128-bit divider or a multiplier; cadical, kissat and z3 all
//! timed out, even on 20-bit operands). Those properties are pinned by `tests/semantics.rs`,
//! run under Miri, and by the differential sweep against the reference, which is where the
//! design document places agreement anyway.

use crate::descriptor::{INT_ABS_LIMIT, LIST_LEN_LIMIT};
use crate::interp::{
    arith, bounded, charge_for, compare, list_len_ok, range_span, unary, State, TrapKind,
};
use crate::term::Op;
use crate::value::{value_cost, Value};

/// A K0 integer: any `i128` within the ADR-0008 bound.
fn any_k0_int() -> i128 {
    let x: i128 = kani::any();
    kani::assume(x >= -INT_ABS_LIMIT && x <= INT_ABS_LIMIT);
    x
}

fn assert_bounded_or_trap(r: Result<i128, TrapKind>) {
    match r {
        Ok(v) => assert!(v >= -INT_ABS_LIMIT && v <= INT_ABS_LIMIT, "an in-bound result"),
        Err(TrapKind::ValueTooLarge) => {}
        Err(other) => panic!("unexpected trap {:?}", other),
    }
}

// -- integer bound (ADR-0008 decision 1) -------------------------------------------------------

#[kani::proof]
fn bounded_is_exactly_the_k0_bound() {
    // Stated without `abs()`: `i128::MIN.abs()` overflows, and the harness must not itself
    // contain the arithmetic it is checking the kernel avoids.
    let v: i128 = kani::any();
    let in_bound = v >= -INT_ABS_LIMIT && v <= INT_ABS_LIMIT;
    match bounded(v) {
        Ok(w) => assert!(w == v && in_bound),
        Err(k) => assert!(k == TrapKind::ValueTooLarge && !in_bound),
    }
}

#[kani::proof]
fn add_is_total_and_bounded() {
    assert_bounded_or_trap(arith(Op::Add, any_k0_int(), any_k0_int()));
}

#[kani::proof]
fn sub_is_total_and_bounded() {
    assert_bounded_or_trap(arith(Op::Sub, any_k0_int(), any_k0_int()));
}

#[kani::proof]
fn mul_is_total_and_bounded() {
    assert_bounded_or_trap(arith(Op::Mul, any_k0_int(), any_k0_int()));
}

#[kani::proof]
fn neg_and_abs_are_total_and_bounded() {
    let a = any_k0_int();
    assert_bounded_or_trap(unary(Op::Neg, a));
    assert_bounded_or_trap(unary(Op::Abs, a));
    // Within the bound neither can trap: the bound is symmetric.
    assert!(unary(Op::Neg, a) == Ok(-a));
    assert!(unary(Op::Abs, a) == Ok(a.abs()));
}

#[kani::proof]
fn min_and_max_never_trap_and_pick_an_operand() {
    let (a, b) = (any_k0_int(), any_k0_int());
    let lo = arith(Op::Min, a, b);
    let hi = arith(Op::Max, a, b);
    assert!(lo == Ok(a) || lo == Ok(b));
    assert!(hi == Ok(a) || hi == Ok(b));
    assert!(lo.unwrap() <= hi.unwrap());
}

// -- division (ADR-0008 decision 2) -----------------------------------------------------------
//
// Split into what a bit-blasting checker can do in budget: the zero-divisor trap, totality and
// the bound for both `div` and `mod`, and for `mod` the sign and magnitude of the remainder.
// The direction of rounding of `div` is Rust's `/` (truncating, by the language reference) and
// is pinned against the Python reference by `tests/semantics.rs` and the differential sweep;
// relating `q` back to `a` and `b` inside a harness is over budget (see the module comment).

#[kani::proof]
fn div_and_mod_trap_exactly_on_a_zero_divisor() {
    let a = any_k0_int();
    assert!(matches!(arith(Op::Div, a, 0), Err(TrapKind::DivisionByZero)));
    assert!(matches!(arith(Op::Mod, a, 0), Err(TrapKind::DivisionByZero)));
}

#[kani::proof]
fn div_by_a_nonzero_divisor_is_total_and_bounded() {
    let (a, b) = (any_k0_int(), any_k0_int());
    kani::assume(b != 0);
    match arith(Op::Div, a, b) {
        Ok(q) => assert!(q >= -INT_ABS_LIMIT && q <= INT_ABS_LIMIT),
        Err(k) => panic!("unexpected trap {:?}", k),
    }
}

#[kani::proof]
fn mod_by_a_nonzero_divisor_is_total_and_bounded() {
    let (a, b) = (any_k0_int(), any_k0_int());
    kani::assume(b != 0);
    match arith(Op::Mod, a, b) {
        Ok(r) => assert!(r >= -INT_ABS_LIMIT && r <= INT_ABS_LIMIT),
        Err(k) => panic!("unexpected trap {:?}", k),
    }
}

#[kani::proof]
fn mod_result_has_the_dividends_sign() {
    // The reference's `a - trunc_div(a, b) * b`: zero, or the sign of the dividend.
    let (a, b) = (any_k0_int(), any_k0_int());
    kani::assume(b != 0);
    let r = arith(Op::Mod, a, b).unwrap();
    assert!(r == 0 || (r < 0) == (a < 0));
}

#[kani::proof]
fn mod_result_is_smaller_in_magnitude_than_the_divisor() {
    let (a, b) = (any_k0_int(), any_k0_int());
    kani::assume(b != 0);
    let r = arith(Op::Mod, a, b).unwrap();
    let (rm, bm) = (if r < 0 { -r } else { r }, if b < 0 { -b } else { b });
    assert!(rm < bm);
}

#[kani::proof]
fn comparisons_never_trap_and_are_the_integer_order() {
    let (a, b) = (any_k0_int(), any_k0_int());
    assert!(compare(Op::Lt, a, b) == Ok(a < b));
    assert!(compare(Op::Le, a, b) == Ok(a <= b));
    assert!(compare(Op::Gt, a, b) == Ok(a > b));
    assert!(compare(Op::Ge, a, b) == Ok(a >= b));
}

// -- list bound --------------------------------------------------------------------------------

#[kani::proof]
fn list_length_check_is_exactly_the_k0_limit() {
    let len: usize = kani::any();
    match list_len_ok(len) {
        Ok(()) => assert!(len <= LIST_LEN_LIMIT),
        Err(k) => assert!(k == TrapKind::ListTooLong && len > LIST_LEN_LIMIT),
    }
}

#[kani::proof]
fn range_span_traps_beyond_the_limit_and_is_the_length_otherwise() {
    let (lo, hi) = (any_k0_int(), any_k0_int());
    match range_span(lo, hi) {
        Err(k) => assert!(k == TrapKind::ListTooLong && hi - lo > LIST_LEN_LIMIT as i128),
        Ok(n) => {
            assert!(hi - lo <= LIST_LEN_LIMIT as i128);
            assert!(n as i128 == if hi > lo { hi - lo } else { 0 });
        }
    }
}

// -- fuel: never decreases, traps exactly at the budget, charges the ADR-0008 cost model -------

#[kani::proof]
fn tick_increases_steps_by_one_and_traps_exactly_when_over_budget() {
    let mut st = State::new(kani::any(), kani::any());
    st.steps = kani::any();
    let before = st;
    let r = st.tick();
    assert!(st.steps >= before.steps, "fuel spent never comes back");
    match before.steps.checked_add(1) {
        None => assert!(r == Err(TrapKind::FuelExhausted)),
        Some(after) => {
            assert!(st.steps == after);
            assert!(r.is_ok() == (after <= before.fuel));
            if r.is_err() {
                assert!(r == Err(TrapKind::FuelExhausted));
            }
        }
    }
}

#[kani::proof]
fn charge_adds_exactly_the_units_and_traps_exactly_when_over_budget() {
    let mut st = State::new(kani::any(), kani::any());
    st.steps = kani::any();
    let units: u64 = kani::any();
    let before = st;
    let r = st.charge(units);
    assert!(st.steps >= before.steps, "fuel spent never comes back");
    if units == 0 {
        assert!(r.is_ok() && st.steps == before.steps, "zero units is a no-op, as in the reference");
    } else {
        match before.steps.checked_add(units) {
            None => assert!(r == Err(TrapKind::FuelExhausted)),
            Some(after) => {
                assert!(st.steps == after);
                assert!(r.is_ok() == (after <= before.fuel));
            }
        }
    }
}

#[kani::proof]
fn cost_model_is_adr_0008() {
    let n: usize = kani::any();
    let m: usize = kani::any();
    kani::assume(n <= LIST_LEN_LIMIT && m <= LIST_LEN_LIMIT);
    assert!(charge_for(Op::Cons, &[n]) == n as u64, "cons charges the length of the list consed onto");
    assert!(charge_for(Op::Tail, &[n]) == n.saturating_sub(1) as u64, "tail charges max(0, len - 1)");
    assert!(charge_for(Op::Append, &[n, m]) == (n + m) as u64, "append charges both lengths");
    assert!(charge_for(Op::Map, &[n]) == n as u64);
    assert!(charge_for(Op::Filter, &[n]) == n as u64);
    assert!(charge_for(Op::Fold, &[n]) == n as u64);
    // Operations without a size term charge nothing beyond their tick.
    assert!(charge_for(Op::Add, &[n, m]) == 0);
    assert!(charge_for(Op::Head, &[n]) == 0);
    assert!(charge_for(Op::Length, &[n]) == 0);
}

// -- `eq` charges one unit per cell of each operand (ADR-0008 cost model) ---------------------
//
// Only the scalar and empty-list shapes verify in budget: any `Box<Value>` or non-empty
// `Vec<Value>` puts the checker on a symbolic heap and over 60 s, whether `value_cost` is
// written recursively or with an explicit worklist (both were tried). Compound costs are
// pinned by `tests/semantics.rs` (a fold's charges) and the differential sweep.

#[kani::proof]
fn scalar_cells_cost_one() {
    assert!(value_cost(&Value::Int(any_k0_int())) == 1);
    assert!(value_cost(&Value::Bool(kani::any())) == 1);
    assert!(value_cost(&Value::Nothing) == 1);
}

#[kani::proof]
#[kani::unwind(2)]
fn an_empty_list_costs_one() {
    assert!(value_cost(&Value::List(vec![])) == 1);
}
