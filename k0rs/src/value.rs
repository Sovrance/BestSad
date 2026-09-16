//! K0 runtime values (`kernel/values.py`).
//!
//! `Bool` and `Int` are distinct variants so the Python `bool <: int` hazard cannot recur.
//! Equality is the structural equality `eq` uses; closures compare by parameters and body, as
//! the reference's byte encoding does, and never by captured environment.

use crate::term::Term;

#[derive(Clone, Debug)]
pub enum Value {
    Int(i128),
    Bool(bool),
    List(Vec<Value>),
    Pair(Box<Value>, Box<Value>),
    Just(Box<Value>),
    Nothing,
    Closure(Box<Closure>),
}

/// A K0 closure. Only ever constructed by `lam` in a higher-order operand position.
#[derive(Clone, Debug)]
pub struct Closure {
    pub params: Vec<String>,
    pub body: Term,
    pub env: Env,
}

/// The evaluation environment. Later bindings shadow earlier ones, which is exactly what the
/// reference's `dict.update` gives; lookup therefore scans from the end.
#[derive(Clone, Debug, Default)]
pub struct Env(Vec<(String, Value)>);

impl Env {
    pub fn new() -> Self {
        Env(Vec::new())
    }

    pub fn get(&self, name: &str) -> Option<&Value> {
        self.0.iter().rev().find(|(n, _)| n == name).map(|(_, v)| v)
    }

    pub fn bind(&mut self, name: &str, value: Value) {
        self.0.push((name.to_string(), value));
    }
}

/// Structural equality (`values.value_equal`): the encoding is injective over the value domain,
/// so equal encodings are equal values and vice versa.
pub fn value_equal(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Int(x), Value::Int(y)) => x == y,
        (Value::Bool(x), Value::Bool(y)) => x == y,
        (Value::List(xs), Value::List(ys)) => {
            xs.len() == ys.len() && xs.iter().zip(ys).all(|(x, y)| value_equal(x, y))
        }
        (Value::Pair(a1, a2), Value::Pair(b1, b2)) => value_equal(a1, b1) && value_equal(a2, b2),
        (Value::Just(x), Value::Just(y)) => value_equal(x, y),
        (Value::Nothing, Value::Nothing) => true,
        (Value::Closure(f), Value::Closure(g)) => f.params == g.params && f.body == g.body,
        _ => false,
    }
}

/// Number of scalar cells in a value: the unit structural comparison is charged in
/// (`interpreter._value_cost`, ADR-0008 decision 3).
pub fn value_cost(v: &Value) -> u64 {
    match v {
        Value::List(xs) => 1 + xs.iter().map(value_cost).sum::<u64>(),
        Value::Pair(a, b) => 1 + value_cost(a) + value_cost(b),
        Value::Just(x) => 1 + value_cost(x),
        _ => 1,
    }
}
