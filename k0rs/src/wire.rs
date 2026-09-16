//! The JSON line protocol between `bestsad.verify.twin` and the `k0rs run` binary.
//!
//! One request per line, one response per line. Integers travel as decimal strings so nothing
//! is lost to a JSON number parser; a literal that does not fit `i128` is kept as `TooLarge`
//! and traps `value_too_large` when evaluated, as the reference's `_bounded` would.

use serde::{Deserialize, Serialize};

use crate::interp::{Kernel, TrapKind};
use crate::term::{IntLit, Op, Program, Term};
use crate::value::Value;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub enum WireValue {
    Int(String),
    Bool(bool),
    List(Vec<WireValue>),
    Pair(Box<WireValue>, Box<WireValue>),
    Some(Box<WireValue>),
    None,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct WireAttrs {
    #[serde(default)]
    pub value: Option<serde_json::Value>,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub elem_type: Option<String>,
    #[serde(default)]
    pub params: Option<Vec<(String, String)>>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct WireTerm {
    pub op: String,
    #[serde(default)]
    pub args: Vec<WireTerm>,
    #[serde(default)]
    pub attrs: WireAttrs,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Request {
    pub params: Vec<(String, String)>,
    pub body: WireTerm,
    #[serde(default)]
    pub fuel: Option<u64>,
    #[serde(default)]
    pub depth_limit: Option<u32>,
    pub inputs: Vec<WireValue>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Response {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ok: Option<WireValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trap: Option<&'static str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub steps: u64,
}

pub fn parse_int_literal(v: &serde_json::Value) -> Result<IntLit, String> {
    match v {
        serde_json::Value::String(s) => Ok(match s.trim().parse::<i128>() {
            Ok(n) => IntLit::Fits(n),
            Err(_) if s.trim().chars().skip_while(|c| *c == '-').all(|c| c.is_ascii_digit())
                && !s.trim().is_empty() => IntLit::TooLarge,
            Err(e) => return Err(format!("const_int value {s:?}: {e}")),
        }),
        serde_json::Value::Number(n) => n
            .as_i64()
            .map(|n| IntLit::Fits(n as i128))
            .or_else(|| n.as_u64().map(|n| IntLit::Fits(n as i128)))
            .ok_or_else(|| format!("const_int value {n} is not an integer")),
        other => Err(format!("const_int value must be an integer, got {other}")),
    }
}

pub fn term_from_wire(w: &WireTerm) -> Result<Term, String> {
    let op = Op::parse(&w.op).ok_or_else(|| format!("unknown operation {:?}", w.op))?;
    let mut args = Vec::with_capacity(w.args.len());
    for a in &w.args {
        args.push(term_from_wire(a)?);
    }
    let mut term = Term::new(op, args);
    match op {
        Op::ConstInt => {
            let v = w.attrs.value.as_ref().ok_or("const_int without a value")?;
            term.int_value = Some(parse_int_literal(v)?);
        }
        Op::ConstBool => match &w.attrs.value {
            Some(serde_json::Value::Bool(b)) => term.bool_value = Some(*b),
            other => return Err(format!("const_bool value must be a bool, got {other:?}")),
        },
        Op::Var => term.name = Some(w.attrs.name.clone().ok_or("var without a name")?),
        Op::Lam => {
            let params = w.attrs.params.as_ref().ok_or("lam without params")?;
            term.params = params.iter().map(|(n, _)| n.clone()).collect();
        }
        _ => {}
    }
    Ok(term)
}

pub fn value_from_wire(w: &WireValue) -> Result<Value, String> {
    Ok(match w {
        WireValue::Int(s) => {
            Value::Int(s.parse::<i128>().map_err(|e| format!("input int {s:?}: {e}"))?)
        }
        WireValue::Bool(b) => Value::Bool(*b),
        WireValue::List(xs) => {
            Value::List(xs.iter().map(value_from_wire).collect::<Result<_, _>>()?)
        }
        WireValue::Pair(a, b) => Value::Pair(Box::new(value_from_wire(a)?), Box::new(value_from_wire(b)?)),
        WireValue::Some(x) => Value::Just(Box::new(value_from_wire(x)?)),
        WireValue::None => Value::Nothing,
    })
}

pub fn value_to_wire(v: &Value) -> Result<WireValue, String> {
    Ok(match v {
        Value::Int(n) => WireValue::Int(n.to_string()),
        Value::Bool(b) => WireValue::Bool(*b),
        Value::List(xs) => WireValue::List(xs.iter().map(value_to_wire).collect::<Result<_, _>>()?),
        Value::Pair(a, b) => WireValue::Pair(Box::new(value_to_wire(a)?), Box::new(value_to_wire(b)?)),
        Value::Just(x) => WireValue::Some(Box::new(value_to_wire(x)?)),
        Value::Nothing => WireValue::None,
        Value::Closure(_) => return Err("a closure is not a data value and cannot cross the wire".into()),
    })
}

/// Parse one request line. serde_json's default recursion limit (128) is below K0's default
/// depth limit (256), so a legitimately deep term would be refused at the door; the limit is
/// lifted and the caller (`k0rs run`) supplies the stack instead.
pub fn parse_request(line: &str) -> Result<Request, serde_json::Error> {
    let mut de = serde_json::Deserializer::from_str(line);
    de.disable_recursion_limit();
    let req = Request::deserialize(&mut de)?;
    de.end()?;
    Ok(req)
}

/// Serve one request. Errors in the request itself (not K0 traps) are reported in `error`.
pub fn serve(req: &Request) -> Response {
    let body = match term_from_wire(&req.body) {
        Ok(t) => t,
        Err(e) => return Response { ok: None, trap: None, error: Some(e), steps: 0 },
    };
    let inputs: Result<Vec<Value>, String> = req.inputs.iter().map(value_from_wire).collect();
    let inputs = match inputs {
        Ok(v) => v,
        Err(e) => return Response { ok: None, trap: None, error: Some(e), steps: 0 },
    };
    let program = Program { params: req.params.iter().map(|(n, _)| n.clone()).collect(), body };
    let kernel = Kernel {
        fuel: req.fuel.unwrap_or(crate::descriptor::DEFAULT_FUEL),
        depth_limit: req.depth_limit.unwrap_or(crate::descriptor::DEFAULT_DEPTH_LIMIT),
    };
    let run = kernel.execute(&program, &inputs, None);
    match run.outcome {
        Ok(v) => match value_to_wire(&v) {
            Ok(w) => Response { ok: Some(w), trap: None, error: None, steps: run.steps },
            Err(e) => Response { ok: None, trap: None, error: Some(e), steps: run.steps },
        },
        Err(kind) => Response { ok: None, trap: Some(kind.as_str()), error: None, steps: run.steps },
    }
}

pub fn trap_name(kind: TrapKind) -> &'static str {
    kind.as_str()
}
