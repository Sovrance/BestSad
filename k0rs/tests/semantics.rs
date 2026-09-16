//! Pins for the semantics the twin must share with the reference, checkable without Python.
//! The authoritative agreement check is the differential sweep in `tests/verify/test_k0_twin.py`.

use k0rs::{Kernel, Op, Program, Term, TrapKind, Value};

fn run(program: &Program, inputs: &[Value]) -> k0rs::Execution {
    Kernel::default().execute(program, inputs, None)
}

fn int_prog(body: Term, params: &[&str]) -> Program {
    Program { params: params.iter().map(|p| p.to_string()).collect(), body }
}

#[test]
fn the_kernel_hash_is_the_python_pin() {
    assert_eq!(k0rs::kernel_version_hash(), k0rs::PYTHON_KERNEL_VERSION_HASH);
    assert_eq!(k0rs::canonical_descriptor().len(), 4524);
}

#[test]
fn div_and_mod_truncate_toward_zero() {
    let div = int_prog(Term::app(Op::Div, vec![Term::var("a"), Term::var("b")]), &["a", "b"]);
    let modp = int_prog(Term::app(Op::Mod, vec![Term::var("a"), Term::var("b")]), &["a", "b"]);
    let v = |p: &Program, a: i128, b: i128| run(p, &[Value::Int(a), Value::Int(b)]).outcome;
    assert!(matches!(v(&div, -7, 2), Ok(Value::Int(-3))));
    assert!(matches!(v(&div, 7, -2), Ok(Value::Int(-3))));
    assert!(matches!(v(&modp, -7, 2), Ok(Value::Int(-1))));
    assert!(matches!(v(&modp, 7, -2), Ok(Value::Int(1))));
    assert_eq!(v(&div, 1, 0).unwrap_err(), TrapKind::DivisionByZero);
    assert_eq!(v(&modp, 1, 0).unwrap_err(), TrapKind::DivisionByZero);
}

#[test]
fn and_is_strict_and_if_is_not() {
    let div0 = Term::app(Op::Div, vec![Term::const_int(1), Term::const_int(0)]);
    let strict = int_prog(
        Term::app(Op::And, vec![Term::const_bool(false), Term::app(Op::Lt, vec![div0.clone(), Term::const_int(1)])]),
        &[],
    );
    assert_eq!(run(&strict, &[]).outcome.unwrap_err(), TrapKind::DivisionByZero);
    let lazy = int_prog(Term::app(Op::If, vec![Term::const_bool(false), div0, Term::const_int(0)]), &[]);
    assert!(matches!(run(&lazy, &[]).outcome, Ok(Value::Int(0))));
}

#[test]
fn the_first_trap_wins_left_to_right() {
    let div0 = Term::app(Op::Div, vec![Term::const_int(1), Term::const_int(0)]);
    let big = Term::app(Op::Mul, vec![Term::const_int(1 << 40), Term::const_int(1 << 40)]);
    let left = int_prog(Term::app(Op::Add, vec![div0.clone(), big.clone()]), &[]);
    let right = int_prog(Term::app(Op::Add, vec![big, div0]), &[]);
    assert_eq!(run(&left, &[]).outcome.unwrap_err(), TrapKind::DivisionByZero);
    assert_eq!(run(&right, &[]).outcome.unwrap_err(), TrapKind::ValueTooLarge);
}

#[test]
fn the_integer_bound_is_inclusive_at_two_to_the_64() {
    let sq = Term::app(Op::Mul, vec![Term::var("x"), Term::var("x")]);
    let fourth = int_prog(Term::app(Op::Mul, vec![sq.clone(), sq]), &["x"]);
    assert!(matches!(run(&fourth, &[Value::Int(1 << 16)]).outcome, Ok(Value::Int(v)) if v == 1i128 << 64));
    assert_eq!(run(&fourth, &[Value::Int(1 << 17)]).outcome.unwrap_err(), TrapKind::ValueTooLarge);
}

#[test]
fn range_traps_beyond_the_list_limit_and_charges_its_span() {
    let range = int_prog(Term::app(Op::Range, vec![Term::var("lo"), Term::var("hi")]), &["lo", "hi"]);
    let ok = run(&range, &[Value::Int(0), Value::Int(4)]);
    assert!(matches!(ok.outcome, Ok(Value::List(ref xs)) if xs.len() == 4));
    // range + two vars = 3 ticks, plus the span of 4.
    assert_eq!(ok.steps, 7);
    let too_long = run(&range, &[Value::Int(0), Value::Int(4097)]);
    assert_eq!(too_long.outcome.unwrap_err(), TrapKind::ListTooLong);
    assert_eq!(too_long.steps, 3, "the trap fires before the span is charged");
    assert!(matches!(run(&range, &[Value::Int(0), Value::Int(4096)]).outcome, Ok(Value::List(_))));
}

#[test]
fn fuel_exhaustion_is_a_trap_with_the_reference_step_count() {
    let add = int_prog(Term::app(Op::Add, vec![Term::var("x"), Term::var("y")]), &["x", "y"]);
    let run = Kernel::default().execute(&add, &[Value::Int(1), Value::Int(2)], Some(2));
    assert_eq!(run.outcome.unwrap_err(), TrapKind::FuelExhausted);
    assert_eq!(run.steps, 3);
}

#[test]
fn a_fold_charges_its_length_and_calls_in_order() {
    // fold(lam(acc, x) -> add(acc, x), 0, [1, 2, 3]) == 6
    let body = Term::app(Op::Add, vec![Term::var("acc"), Term::var("x")]);
    let fold = int_prog(
        Term::app(Op::Fold, vec![Term::lam(&["acc", "x"], body), Term::const_int(0), Term::var("xs")]),
        &["xs"],
    );
    let xs = Value::List(vec![Value::Int(1), Value::Int(2), Value::Int(3)]);
    let run = run(&fold, &[xs]);
    assert!(matches!(run.outcome, Ok(Value::Int(6))));
    // fold, lam, const, var = 4 ticks; charge 3; three calls of add(acc, x) = 3 ticks each.
    assert_eq!(run.steps, 4 + 3 + 9);
}

#[test]
fn depth_is_bounded_and_traps() {
    // 300 nested `neg`s exceed the default depth limit of 256.
    let mut t = Term::var("x");
    for _ in 0..300 {
        t = Term::app(Op::Neg, vec![t]);
    }
    let deep = int_prog(t, &["x"]);
    assert_eq!(run(&deep, &[Value::Int(1)]).outcome.unwrap_err(), TrapKind::DepthExceeded);
}

#[test]
fn the_wire_protocol_round_trips_a_request() {
    let req = r#"{"params":[["x","Int"]],"body":{"op":"add","args":[{"op":"var","attrs":{"name":"x"}},{"op":"const_int","attrs":{"value":"1"}}]},"inputs":[{"Int":"41"}]}"#;
    let parsed: k0rs::wire::Request = serde_json::from_str(req).unwrap();
    let resp = k0rs::wire::serve(&parsed);
    assert_eq!(serde_json::to_string(&resp).unwrap(), r#"{"ok":{"Int":"42"},"steps":3}"#);

    let huge = r#"{"params":[],"body":{"op":"const_int","attrs":{"value":"1000000000000000000000000000000000000000000000"}},"inputs":[]}"#;
    let parsed: k0rs::wire::Request = serde_json::from_str(huge).unwrap();
    let resp = k0rs::wire::serve(&parsed);
    assert_eq!(resp.trap, Some("value_too_large"));
}
