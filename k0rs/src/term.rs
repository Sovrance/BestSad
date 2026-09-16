//! K0 program terms (`kernel/terms.py`), with the operation resolved to an enum at load time so
//! the interpreter dispatches on a tag rather than a string.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Op {
    ConstInt,
    ConstBool,
    Var,
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    Neg,
    Abs,
    Min,
    Max,
    Eq,
    Lt,
    Le,
    Gt,
    Ge,
    And,
    Or,
    Not,
    If,
    Tuple,
    Fst,
    Snd,
    Nil,
    Cons,
    Head,
    Tail,
    Length,
    Index,
    Append,
    Range,
    Some_,
    None_,
    OptionGetOr,
    IsSome,
    Map,
    Filter,
    Fold,
    Lam,
}

impl Op {
    pub fn parse(name: &str) -> Option<Op> {
        Some(match name {
            "const_int" => Op::ConstInt,
            "const_bool" => Op::ConstBool,
            "var" => Op::Var,
            "add" => Op::Add,
            "sub" => Op::Sub,
            "mul" => Op::Mul,
            "div" => Op::Div,
            "mod" => Op::Mod,
            "neg" => Op::Neg,
            "abs" => Op::Abs,
            "min" => Op::Min,
            "max" => Op::Max,
            "eq" => Op::Eq,
            "lt" => Op::Lt,
            "le" => Op::Le,
            "gt" => Op::Gt,
            "ge" => Op::Ge,
            "and" => Op::And,
            "or" => Op::Or,
            "not" => Op::Not,
            "if" => Op::If,
            "tuple" => Op::Tuple,
            "fst" => Op::Fst,
            "snd" => Op::Snd,
            "nil" => Op::Nil,
            "cons" => Op::Cons,
            "head" => Op::Head,
            "tail" => Op::Tail,
            "length" => Op::Length,
            "index" => Op::Index,
            "append" => Op::Append,
            "range" => Op::Range,
            "some" => Op::Some_,
            "none" => Op::None_,
            "option_get_or" => Op::OptionGetOr,
            "is_some" => Op::IsSome,
            "map" => Op::Map,
            "filter" => Op::Filter,
            "fold" => Op::Fold,
            "lam" => Op::Lam,
            _ => return None,
        })
    }

    pub fn name(self) -> &'static str {
        match self {
            Op::ConstInt => "const_int",
            Op::ConstBool => "const_bool",
            Op::Var => "var",
            Op::Add => "add",
            Op::Sub => "sub",
            Op::Mul => "mul",
            Op::Div => "div",
            Op::Mod => "mod",
            Op::Neg => "neg",
            Op::Abs => "abs",
            Op::Min => "min",
            Op::Max => "max",
            Op::Eq => "eq",
            Op::Lt => "lt",
            Op::Le => "le",
            Op::Gt => "gt",
            Op::Ge => "ge",
            Op::And => "and",
            Op::Or => "or",
            Op::Not => "not",
            Op::If => "if",
            Op::Tuple => "tuple",
            Op::Fst => "fst",
            Op::Snd => "snd",
            Op::Nil => "nil",
            Op::Cons => "cons",
            Op::Head => "head",
            Op::Tail => "tail",
            Op::Length => "length",
            Op::Index => "index",
            Op::Append => "append",
            Op::Range => "range",
            Op::Some_ => "some",
            Op::None_ => "none",
            Op::OptionGetOr => "option_get_or",
            Op::IsSome => "is_some",
            Op::Map => "map",
            Op::Filter => "filter",
            Op::Fold => "fold",
            Op::Lam => "lam",
        }
    }
}

/// An integer literal as it arrived. The reference bounds literals at evaluation time
/// (`_bounded(term.attr("value"))`), so one that does not even fit `i128` is kept as
/// `TooLarge` and traps `value_too_large` when evaluated, rather than being rejected at load.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IntLit {
    Fits(i128),
    TooLarge,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Term {
    pub op: Op,
    pub args: Vec<Term>,
    /// `const_int` value.
    pub int_value: Option<IntLit>,
    /// `const_bool` value.
    pub bool_value: Option<bool>,
    /// `var` name.
    pub name: Option<String>,
    /// `lam` parameter names, in order. Types are irrelevant at run time.
    pub params: Vec<String>,
}

impl Term {
    pub fn new(op: Op, args: Vec<Term>) -> Term {
        Term { op, args, int_value: None, bool_value: None, name: None, params: Vec::new() }
    }

    pub fn const_int(v: i128) -> Term {
        Term { int_value: Some(IntLit::Fits(v)), ..Term::new(Op::ConstInt, Vec::new()) }
    }

    pub fn const_bool(v: bool) -> Term {
        Term { bool_value: Some(v), ..Term::new(Op::ConstBool, Vec::new()) }
    }

    pub fn var(name: &str) -> Term {
        Term { name: Some(name.to_string()), ..Term::new(Op::Var, Vec::new()) }
    }

    pub fn lam(params: &[&str], body: Term) -> Term {
        Term {
            params: params.iter().map(|p| p.to_string()).collect(),
            ..Term::new(Op::Lam, vec![body])
        }
    }

    pub fn app(op: Op, args: Vec<Term>) -> Term {
        Term::new(op, args)
    }
}

/// A K0 program: parameter names and a body. Parameter types are checked on the Python side
/// (`kernel/typecheck.py`); the twin executes, it does not typecheck.
#[derive(Clone, Debug, PartialEq)]
pub struct Program {
    pub params: Vec<String>,
    pub body: Term,
}
