//! The K0 v1.0.0 evaluator, transcribed from `src/bestsad/kernel/interpreter.py`.
//!
//! Every decision here mirrors a line of the reference, and the order of checks is the
//! reference's order: fuel is charged where the reference charges it, and a trap that the
//! reference raises first is raised first here. Where this file and the reference disagree,
//! this file is wrong (ADR-0002, ADR-0020).
//!
//! The pure pieces -- `bounded`, `list_len_ok`, `arith`, `unary`, `compare`, `charge_for`, and
//! `State::{tick, charge}` -- are factored out so the Kani harnesses in `proofs.rs` can state
//! properties about exactly the code the evaluator runs.

use crate::descriptor::{DEFAULT_DEPTH_LIMIT, DEFAULT_FUEL, INT_ABS_LIMIT, LIST_LEN_LIMIT};
use crate::term::{IntLit, Op, Program, Term};
use crate::value::{value_cost, value_equal, Closure, Env, Value};

/// The closed set of six trap kinds (ADR-0008). Adding one changes K0.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrapKind {
    DivisionByZero,
    FuelExhausted,
    DepthExceeded,
    ValueTooLarge,
    ListTooLong,
    MalformedProgram,
}

impl TrapKind {
    /// The wire spelling, identical to `kernel.traps.TrapKind.value`.
    pub fn as_str(self) -> &'static str {
        match self {
            TrapKind::DivisionByZero => "division_by_zero",
            TrapKind::FuelExhausted => "fuel_exhausted",
            TrapKind::DepthExceeded => "depth_exceeded",
            TrapKind::ValueTooLarge => "value_too_large",
            TrapKind::ListTooLong => "list_too_long",
            TrapKind::MalformedProgram => "malformed_program",
        }
    }
}

pub type Outcome = Result<Value, TrapKind>;

/// Fuel and depth accounting (`interpreter._State`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct State {
    pub fuel: u64,
    pub depth_limit: u32,
    pub steps: u64,
}

impl State {
    pub fn new(fuel: u64, depth_limit: u32) -> State {
        State { fuel, depth_limit, steps: 0 }
    }

    /// `_State.tick`: every evaluated node costs one step; exceeding the budget traps.
    pub fn tick(&mut self) -> Result<(), TrapKind> {
        self.charge(1)
    }

    /// `_State.charge`: work proportional to the size of a list built or traversed, or of the
    /// values `eq` compares. Zero units are a no-op, exactly as in the reference. The sum is
    /// checked rather than wrapping: an overflow is by definition beyond any `u64` budget.
    pub fn charge(&mut self, units: u64) -> Result<(), TrapKind> {
        if units == 0 {
            return Ok(());
        }
        match self.steps.checked_add(units) {
            None => Err(TrapKind::FuelExhausted),
            Some(total) => {
                self.steps = total;
                if total > self.fuel {
                    Err(TrapKind::FuelExhausted)
                } else {
                    Ok(())
                }
            }
        }
    }
}

/// `interpreter._bounded`: the K0 integer bound is `|v| <= 2^64`; beyond it, `value_too_large`.
pub fn bounded(v: i128) -> Result<i128, TrapKind> {
    if !(-INT_ABS_LIMIT..=INT_ABS_LIMIT).contains(&v) {
        Err(TrapKind::ValueTooLarge)
    } else {
        Ok(v)
    }
}

/// `interpreter._bounded_list`, on the length alone: a list may not exceed `LIST_LEN_LIMIT`.
pub fn list_len_ok(len: usize) -> Result<(), TrapKind> {
    if len > LIST_LEN_LIMIT {
        Err(TrapKind::ListTooLong)
    } else {
        Ok(())
    }
}

/// Binary integer arithmetic: `add sub mul div mod min max`.
///
/// A checked `i128` operation that overflows has a true result of magnitude at least 2^127,
/// which is beyond the K0 bound, so overflow maps to `value_too_large`. Division and remainder
/// are Rust's, which truncate toward zero with the dividend's sign on the remainder -- the
/// ADR-0008 decision the reference implements by hand.
pub fn arith(op: Op, a: i128, b: i128) -> Result<i128, TrapKind> {
    match op {
        Op::Add => bounded(a.checked_add(b).ok_or(TrapKind::ValueTooLarge)?),
        Op::Sub => bounded(a.checked_sub(b).ok_or(TrapKind::ValueTooLarge)?),
        Op::Mul => bounded(a.checked_mul(b).ok_or(TrapKind::ValueTooLarge)?),
        Op::Div => {
            if b == 0 {
                return Err(TrapKind::DivisionByZero);
            }
            bounded(a.checked_div(b).ok_or(TrapKind::ValueTooLarge)?)
        }
        Op::Mod => {
            if b == 0 {
                return Err(TrapKind::DivisionByZero);
            }
            // `i128::MIN % -1` overflows in Rust; its mathematical value, and the reference's
            // `a - trunc_div(a, b) * b`, is zero.
            bounded(a.checked_rem(b).unwrap_or(0))
        }
        Op::Min => Ok(if a <= b { a } else { b }),
        Op::Max => Ok(if a >= b { a } else { b }),
        _ => Err(TrapKind::MalformedProgram),
    }
}

/// Unary integer arithmetic: `neg abs`.
pub fn unary(op: Op, a: i128) -> Result<i128, TrapKind> {
    match op {
        Op::Neg => bounded(a.checked_neg().ok_or(TrapKind::ValueTooLarge)?),
        Op::Abs => bounded(a.checked_abs().ok_or(TrapKind::ValueTooLarge)?),
        _ => Err(TrapKind::MalformedProgram),
    }
}

/// Integer comparison: `lt le gt ge`.
pub fn compare(op: Op, a: i128, b: i128) -> Result<bool, TrapKind> {
    match op {
        Op::Lt => Ok(a < b),
        Op::Le => Ok(a <= b),
        Op::Gt => Ok(a > b),
        Op::Ge => Ok(a >= b),
        _ => Err(TrapKind::MalformedProgram),
    }
}

/// The ADR-0008 cost model: the units an operation charges beyond its one-step tick, given
/// the lengths it builds or traverses. Every `charge` call in `apply` goes through here, so a
/// proof about this function is a proof about what the evaluator charges.
pub fn charge_for(op: Op, lens: &[usize]) -> u64 {
    match (op, lens) {
        (Op::Cons, [xs]) => *xs as u64,
        (Op::Tail, [xs]) => xs.saturating_sub(1) as u64,
        (Op::Append, [a, b]) => (*a as u64) + (*b as u64),
        (Op::Map, [xs]) | (Op::Filter, [xs]) | (Op::Fold, [xs]) => *xs as u64,
        _ => 0,
    }
}

/// `range` charges `max(0, hi - lo)`, after the `LIST_TOO_LONG` check on the span.
pub fn range_span(lo: i128, hi: i128) -> Result<u64, TrapKind> {
    let span = hi - lo; // |lo|, |hi| <= 2^64 so this cannot overflow i128
    if span > LIST_LEN_LIMIT as i128 {
        return Err(TrapKind::ListTooLong);
    }
    Ok(if span > 0 { span as u64 } else { 0 })
}

/// The trusted evaluator. Genome primitives (`prim:*`) are macros over K0 and are expanded by
/// the Python kernel before a program crosses to the twin; a term carrying one here is
/// malformed.
pub struct Kernel {
    pub fuel: u64,
    pub depth_limit: u32,
}

impl Default for Kernel {
    fn default() -> Self {
        Kernel { fuel: DEFAULT_FUEL, depth_limit: DEFAULT_DEPTH_LIMIT }
    }
}

/// The result of one execution: the outcome and the steps it took (`ExecutionResult.steps`).
#[derive(Clone, Debug)]
pub struct Execution {
    pub outcome: Outcome,
    pub steps: u64,
}

impl Kernel {
    pub fn execute(&self, program: &Program, inputs: &[Value], fuel: Option<u64>) -> Execution {
        if inputs.len() != program.params.len() {
            return Execution { outcome: Err(TrapKind::MalformedProgram), steps: 0 };
        }
        let mut env = Env::new();
        for (name, value) in program.params.iter().zip(inputs) {
            env.bind(name, value.clone());
        }
        let mut st = State::new(fuel.unwrap_or(self.fuel), self.depth_limit);
        let outcome = self.eval(&program.body, &env, &mut st, 0);
        Execution { outcome, steps: st.steps }
    }

    fn eval(&self, term: &Term, env: &Env, st: &mut State, depth: u32) -> Outcome {
        if depth > st.depth_limit {
            return Err(TrapKind::DepthExceeded);
        }
        st.tick()?;
        match term.op {
            // -- the only non-strict operation --
            Op::If => {
                let cond = self.eval(arg(term, 0)?, env, st, depth + 1)?;
                let branch = if truthy(&cond)? { arg(term, 1)? } else { arg(term, 2)? };
                self.eval(branch, env, st, depth + 1)
            }
            Op::Lam => Ok(Value::Closure(Box::new(Closure {
                params: term.params.clone(),
                body: arg(term, 0)?.clone(),
                env: env.clone(),
            }))),
            // -- strict operations: operands left to right, then apply --
            _ => {
                let mut args = Vec::with_capacity(term.args.len());
                for a in &term.args {
                    args.push(self.eval(a, env, st, depth + 1)?);
                }
                self.apply(term, args, env, st, depth)
            }
        }
    }

    fn apply(&self, term: &Term, a: Vec<Value>, env: &Env, st: &mut State, depth: u32) -> Outcome {
        use Value::*;
        match term.op {
            Op::ConstInt => match term.int_value {
                Some(IntLit::Fits(v)) => Ok(Int(bounded(v)?)),
                Some(IntLit::TooLarge) => Err(TrapKind::ValueTooLarge),
                None => Err(TrapKind::MalformedProgram),
            },
            Op::ConstBool => Ok(Bool(term.bool_value.ok_or(TrapKind::MalformedProgram)?)),
            Op::Var => {
                let name = term.name.as_deref().ok_or(TrapKind::MalformedProgram)?;
                env.get(name).cloned().ok_or(TrapKind::MalformedProgram)
            }

            // first-order: no evaluation, no environment, no recursion (see apply_first_order)
            Op::Add | Op::Sub | Op::Mul | Op::Div | Op::Mod | Op::Min | Op::Max | Op::Neg
            | Op::Abs | Op::Eq | Op::Lt | Op::Le | Op::Gt | Op::Ge | Op::And | Op::Or | Op::Not
            | Op::Tuple | Op::Fst | Op::Snd | Op::Nil | Op::Cons | Op::Head | Op::Tail
            | Op::Length | Op::Index | Op::Append | Op::Range | Op::Some_ | Op::None_
            | Op::OptionGetOr | Op::IsSome => apply_first_order(term.op, a, st),

            // higher-order
            Op::Map => {
                let f = closure(&a, 0)?;
                let xs = list(&a, 1)?;
                st.charge(charge_for(Op::Map, &[xs.len()]))?;
                let mut out = Vec::with_capacity(xs.len());
                for x in xs {
                    out.push(self.call(f, std::slice::from_ref(x), st, depth)?);
                }
                list_len_ok(out.len())?;
                Ok(List(out))
            }
            Op::Filter => {
                let f = closure(&a, 0)?;
                let xs = list(&a, 1)?;
                st.charge(charge_for(Op::Filter, &[xs.len()]))?;
                let mut out = Vec::new();
                for x in xs {
                    if truthy(&self.call(f, std::slice::from_ref(x), st, depth)?)? {
                        out.push(x.clone());
                    }
                }
                Ok(List(out))
            }
            Op::Fold => {
                let f = closure(&a, 0)?;
                let xs = list(&a, 2)?;
                st.charge(charge_for(Op::Fold, &[xs.len()]))?;
                let mut acc = get(&a, 1)?.clone();
                for x in xs {
                    acc = self.call(f, &[acc, x.clone()], st, depth)?;
                }
                Ok(acc)
            }

            Op::If | Op::Lam => Err(TrapKind::MalformedProgram), // handled in `eval`
        }
    }

    /// `Kernel._call`: the closure's captured environment, then its parameters, then the body
    /// one level deeper than the caller.
    fn call(&self, f: &Closure, args: &[Value], st: &mut State, depth: u32) -> Outcome {
        let mut env = f.env.clone();
        for (name, value) in f.params.iter().zip(args) {
            env.bind(name, value.clone());
        }
        self.eval(&f.body, &env, st, depth + 1)
    }
}

/// Every first-order operation: given already-evaluated operands, produce a value or a trap.
///
/// No evaluation, no environment and no recursion happen here -- `if`, `lam`, `var`, the
/// constants and the higher-order operations (`map`, `filter`, `fold`) are in `Kernel::apply`.
/// The charges are exactly those the reference's `_apply` makes, in the same order relative to
/// the checks. Kani harnesses over this function were tried and exceed the 60 s budget (the
/// `Vec<Value>` operands and their drop glue are modelled on a symbolic heap), so the per-op
/// proofs in `proofs.rs` are over the pure functions this one calls -- `arith`, `unary`,
/// `compare`, `list_len_ok`, `range_span`, `charge_for`, `value_cost` -- and this function is
/// covered by `tests/semantics.rs` and the differential sweep against the reference.
pub fn apply_first_order(op: Op, a: Vec<Value>, st: &mut State) -> Outcome {
    use Value::*;
    match op {
        // arithmetic
        Op::Add | Op::Sub | Op::Mul | Op::Div | Op::Mod | Op::Min | Op::Max => {
            let (x, y) = (int(&a, 0)?, int(&a, 1)?);
            Ok(Int(arith(op, x, y)?))
        }
        Op::Neg | Op::Abs => Ok(Int(unary(op, int(&a, 0)?)?)),

        // comparison
        Op::Eq => {
            let (x, y) = (get(&a, 0)?, get(&a, 1)?);
            st.charge(value_cost(x) + value_cost(y))?;
            Ok(Bool(value_equal(x, y)))
        }
        Op::Lt | Op::Le | Op::Gt | Op::Ge => {
            Ok(Bool(compare(op, int(&a, 0)?, int(&a, 1)?)?))
        }

        // boolean
        Op::And => Ok(Bool(boolean(&a, 0)? && boolean(&a, 1)?)),
        Op::Or => Ok(Bool(boolean(&a, 0)? || boolean(&a, 1)?)),
        Op::Not => Ok(Bool(!boolean(&a, 0)?)),

        // tuples
        Op::Tuple => {
            let mut it = a.into_iter();
            let (x, y) = (it.next(), it.next());
            match (x, y) {
                (Some(x), Some(y)) => Ok(Pair(Box::new(x), Box::new(y))),
                _ => Err(TrapKind::MalformedProgram),
            }
        }
        Op::Fst => match get(&a, 0)? {
            Pair(x, _) => Ok((**x).clone()),
            _ => Err(TrapKind::MalformedProgram),
        },
        Op::Snd => match get(&a, 0)? {
            Pair(_, y) => Ok((**y).clone()),
            _ => Err(TrapKind::MalformedProgram),
        },

        // lists
        Op::Nil => Ok(List(Vec::new())),
        Op::Cons => {
            let xs = list(&a, 1)?;
            st.charge(charge_for(Op::Cons, &[xs.len()]))?;
            list_len_ok(xs.len() + 1)?;
            let mut out = Vec::with_capacity(xs.len() + 1);
            out.push(get(&a, 0)?.clone());
            out.extend(xs.iter().cloned());
            Ok(List(out))
        }
        Op::Head => {
            let xs = list(&a, 0)?;
            Ok(match xs.first() {
                Some(x) => Just(Box::new(x.clone())),
                None => Nothing,
            })
        }
        Op::Tail => {
            let xs = list(&a, 0)?;
            st.charge(charge_for(Op::Tail, &[xs.len()]))?;
            Ok(List(xs.iter().skip(1).cloned().collect()))
        }
        Op::Length => Ok(Int(list(&a, 0)?.len() as i128)),
        Op::Index => {
            let xs = list(&a, 0)?;
            let idx = int(&a, 1)?;
            Ok(if idx >= 0 && idx < xs.len() as i128 {
                Just(Box::new(xs[idx as usize].clone()))
            } else {
                Nothing
            })
        }
        Op::Append => {
            let (xs, ys) = (list(&a, 0)?, list(&a, 1)?);
            st.charge(charge_for(Op::Append, &[xs.len(), ys.len()]))?;
            list_len_ok(xs.len() + ys.len())?;
            let mut out = Vec::with_capacity(xs.len() + ys.len());
            out.extend(xs.iter().cloned());
            out.extend(ys.iter().cloned());
            Ok(List(out))
        }
        Op::Range => {
            let (lo, hi) = (int(&a, 0)?, int(&a, 1)?);
            let span = range_span(lo, hi)?;
            st.charge(span)?;
            Ok(List((0..span).map(|i| Int(lo + i as i128)).collect()))
        }

        // options
        Op::Some_ => Ok(Just(Box::new(get(&a, 0)?.clone()))),
        Op::None_ => Ok(Nothing),
        Op::OptionGetOr => match get(&a, 0)? {
            Just(x) => Ok((**x).clone()),
            _ => Ok(get(&a, 1)?.clone()),
        },
        Op::IsSome => Ok(Bool(matches!(get(&a, 0)?, Just(_)))),
        _ => Err(TrapKind::MalformedProgram), // evaluated in `Kernel::apply`, never here
    }
}

// -- operand access; a type error here is a malformed program, never a panic ------------------

fn arg(term: &Term, i: usize) -> Result<&Term, TrapKind> {
    term.args.get(i).ok_or(TrapKind::MalformedProgram)
}

fn get(a: &[Value], i: usize) -> Result<&Value, TrapKind> {
    a.get(i).ok_or(TrapKind::MalformedProgram)
}

fn int(a: &[Value], i: usize) -> Result<i128, TrapKind> {
    match get(a, i)? {
        Value::Int(v) => Ok(*v),
        _ => Err(TrapKind::MalformedProgram),
    }
}

fn boolean(a: &[Value], i: usize) -> Result<bool, TrapKind> {
    truthy(get(a, i)?)
}

fn truthy(v: &Value) -> Result<bool, TrapKind> {
    match v {
        Value::Bool(b) => Ok(*b),
        _ => Err(TrapKind::MalformedProgram),
    }
}

fn list(a: &[Value], i: usize) -> Result<&Vec<Value>, TrapKind> {
    match get(a, i)? {
        Value::List(xs) => Ok(xs),
        _ => Err(TrapKind::MalformedProgram),
    }
}

fn closure(a: &[Value], i: usize) -> Result<&Closure, TrapKind> {
    match get(a, i)? {
        Value::Closure(f) => Ok(f),
        _ => Err(TrapKind::MalformedProgram),
    }
}
