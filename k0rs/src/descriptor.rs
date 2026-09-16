//! The K0 v1.0.0 operation table and resource limits, and the kernel version hash over them.
//!
//! This is a transcription of `src/bestsad/kernel/ops.py` and `spec.py`. Order is significant:
//! it is part of the hash. `canonical_descriptor` reproduces, byte for byte, Python's
//! `json.dumps(kernel_descriptor(), sort_keys=True, separators=(",", ":"))`, and
//! `kernel_version_hash` is its SHA-256. `build.rs` refuses to build the crate if the result
//! differs from the pinned Python constant, so a transcription error is a build failure rather
//! than a silently different kernel.
//!
//! No dependencies beyond `sha2`, because `build.rs` compiles this file too.

use sha2::{Digest, Sha256};

pub const KERNEL_VERSION: &str = "K0-1.0.0";

/// `|x| <= 2^64`; beyond it the kernel traps `value_too_large` (ADR-0008).
pub const INT_ABS_LIMIT: i128 = 1i128 << 64;
pub const LIST_LEN_LIMIT: usize = 4096;
pub const DEFAULT_FUEL: u64 = 100_000;
pub const DEFAULT_DEPTH_LIMIT: u32 = 256;

/// `tests/kernel/test_frozen.py::PINNED_KERNEL_HASH`. Do not "fix" this to make a build pass.
pub const PYTHON_KERNEL_VERSION_HASH: &str =
    "9aa25728b3b00abc717011a72e9ca7f0a73095f14ceb8e6fc0abc4ded52b3165";

pub struct OpSig {
    pub op: &'static str,
    pub family: &'static str,
    pub params: &'static [&'static str],
    pub ret: &'static str,
    pub attrs: &'static [&'static str],
    pub strict: bool,
    pub traps: &'static [&'static str],
}

const fn sig(
    op: &'static str,
    family: &'static str,
    params: &'static [&'static str],
    ret: &'static str,
    attrs: &'static [&'static str],
    strict: bool,
    traps: &'static [&'static str],
) -> OpSig {
    OpSig { op, family, params, ret, attrs, strict, traps }
}

/// The 40 operations of K0 v1.0.0, in table order.
pub const K0_OPS: [OpSig; 40] = [
    // constants and argument access
    sig("const_int", "const", &[], "Int", &["value"], true, &[]),
    sig("const_bool", "const", &[], "Bool", &["value"], true, &[]),
    sig("var", "const", &[], "'V", &["name"], true, &[]),
    // scalar arithmetic
    sig("add", "arith", &["Int", "Int"], "Int", &[], true, &["value_too_large"]),
    sig("sub", "arith", &["Int", "Int"], "Int", &[], true, &["value_too_large"]),
    sig("mul", "arith", &["Int", "Int"], "Int", &[], true, &["value_too_large"]),
    sig("div", "arith", &["Int", "Int"], "Int", &[], true, &["division_by_zero"]),
    sig("mod", "arith", &["Int", "Int"], "Int", &[], true, &["division_by_zero"]),
    sig("neg", "arith", &["Int"], "Int", &[], true, &["value_too_large"]),
    sig("abs", "arith", &["Int"], "Int", &[], true, &["value_too_large"]),
    sig("min", "arith", &["Int", "Int"], "Int", &[], true, &[]),
    sig("max", "arith", &["Int", "Int"], "Int", &[], true, &[]),
    // comparison
    sig("eq", "cmp", &["'T", "'T"], "Bool", &[], true, &[]),
    sig("lt", "cmp", &["Int", "Int"], "Bool", &[], true, &[]),
    sig("le", "cmp", &["Int", "Int"], "Bool", &[], true, &[]),
    sig("gt", "cmp", &["Int", "Int"], "Bool", &[], true, &[]),
    sig("ge", "cmp", &["Int", "Int"], "Bool", &[], true, &[]),
    // boolean logic
    sig("and", "bool", &["Bool", "Bool"], "Bool", &[], true, &[]),
    sig("or", "bool", &["Bool", "Bool"], "Bool", &[], true, &[]),
    sig("not", "bool", &["Bool"], "Bool", &[], true, &[]),
    // conditional selection: the only non-strict operation
    sig("if", "cond", &["Bool", "'T", "'T"], "'T", &[], false, &[]),
    // tuples
    sig("tuple", "tuple", &["'T", "'U"], "Tuple<'T,'U>", &[], true, &[]),
    sig("fst", "tuple", &["Tuple<'T,'U>"], "'T", &[], true, &[]),
    sig("snd", "tuple", &["Tuple<'T,'U>"], "'U", &[], true, &[]),
    // lists
    sig("nil", "list", &[], "List<'T>", &["elem_type"], true, &[]),
    sig("cons", "list", &["'T", "List<'T>"], "List<'T>", &[], true, &["list_too_long"]),
    sig("head", "list", &["List<'T>"], "Option<'T>", &[], true, &[]),
    sig("tail", "list", &["List<'T>"], "List<'T>", &[], true, &[]),
    sig("length", "list", &["List<'T>"], "Int", &[], true, &[]),
    sig("index", "list", &["List<'T>", "Int"], "Option<'T>", &[], true, &[]),
    sig("append", "list", &["List<'T>", "List<'T>"], "List<'T>", &[], true, &["list_too_long"]),
    sig("range", "list", &["Int", "Int"], "List<Int>", &[], true, &["list_too_long"]),
    // options
    sig("some", "option", &["'T"], "Option<'T>", &[], true, &[]),
    sig("none", "option", &[], "Option<'T>", &["elem_type"], true, &[]),
    sig("option_get_or", "option", &["Option<'T>", "'T"], "'T", &[], true, &[]),
    sig("is_some", "option", &["Option<'T>"], "Bool", &[], true, &[]),
    // structured higher-order iteration
    sig("map", "hof", &["Fun<('T)->'U>", "List<'T>"], "List<'U>", &[], true, &[]),
    sig("filter", "hof", &["Fun<('T)->Bool>", "List<'T>"], "List<'T>", &[], true, &[]),
    sig("fold", "hof", &["Fun<('Acc,'T)->'Acc>", "'Acc", "List<'T>"], "'Acc", &[], true, &[]),
    // constrained closure introduction
    sig("lam", "lam", &["'Body"], "'F", &["params"], true, &[]),
];

fn json_str_list(items: &[&str]) -> String {
    // Every string in the table is plain ASCII with no quotes or backslashes, so no escaping
    // is needed to match Python's encoder. Assert that rather than assume it.
    let mut out = String::from("[");
    for (i, s) in items.iter().enumerate() {
        assert!(
            s.chars().all(|c| c.is_ascii() && c != '"' && c != '\\' && !c.is_ascii_control()),
            "descriptor string needs escaping, which this encoder does not do: {s:?}"
        );
        if i > 0 {
            out.push(',');
        }
        out.push('"');
        out.push_str(s);
        out.push('"');
    }
    out.push(']');
    out
}

/// Python: `json.dumps(kernel_descriptor(), sort_keys=True, separators=(",", ":"))`.
///
/// Keys appear in sorted order at every level: `kernel_version`, `limits`, `operations`;
/// within a limit object `default_depth_limit`, `default_fuel`, `int_abs_limit`,
/// `list_len_limit`; within an operation `attrs`, `family`, `op`, `params`, `ret`, `strict`,
/// `traps`.
pub fn canonical_descriptor() -> String {
    let mut s = String::with_capacity(5000);
    s.push_str("{\"kernel_version\":\"");
    s.push_str(KERNEL_VERSION);
    s.push_str("\",\"limits\":{\"default_depth_limit\":");
    s.push_str(&DEFAULT_DEPTH_LIMIT.to_string());
    s.push_str(",\"default_fuel\":");
    s.push_str(&DEFAULT_FUEL.to_string());
    s.push_str(",\"int_abs_limit\":");
    s.push_str(&INT_ABS_LIMIT.to_string());
    s.push_str(",\"list_len_limit\":");
    s.push_str(&LIST_LEN_LIMIT.to_string());
    s.push_str("},\"operations\":[");
    for (i, o) in K0_OPS.iter().enumerate() {
        if i > 0 {
            s.push(',');
        }
        s.push_str("{\"attrs\":");
        s.push_str(&json_str_list(o.attrs));
        s.push_str(",\"family\":\"");
        s.push_str(o.family);
        s.push_str("\",\"op\":\"");
        s.push_str(o.op);
        s.push_str("\",\"params\":");
        s.push_str(&json_str_list(o.params));
        s.push_str(",\"ret\":\"");
        s.push_str(o.ret);
        s.push_str("\",\"strict\":");
        s.push_str(if o.strict { "true" } else { "false" });
        s.push_str(",\"traps\":");
        s.push_str(&json_str_list(o.traps));
        s.push('}');
    }
    s.push_str("]}");
    s
}

/// SHA-256 of the canonical descriptor, lowercase hex: `bestsad.kernel.spec.kernel_version_hash()`.
pub fn kernel_version_hash() -> String {
    let digest = Sha256::digest(canonical_descriptor().as_bytes());
    let mut hex = String::with_capacity(64);
    for byte in digest {
        hex.push_str(&format!("{byte:02x}"));
    }
    hex
}
