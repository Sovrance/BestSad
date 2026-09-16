//! `k0rs` command line.
//!
//!     k0rs hash          print the kernel version hash (must equal Python's KERNEL_VERSION_HASH)
//!     k0rs descriptor    print the canonical descriptor JSON the hash is taken over
//!     k0rs run           serve JSON-line requests on stdin, one response per line on stdout
//!     k0rs version       crate version

use std::io::{self, BufRead, Write};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("hash") => println!("{}", k0rs::kernel_version_hash()),
        Some("descriptor") => println!("{}", k0rs::canonical_descriptor()),
        Some("version") => println!("k0rs {}", env!("CARGO_PKG_VERSION")),
        Some("run") => run(),
        _ => {
            eprintln!("usage: k0rs hash | descriptor | run | version");
            std::process::exit(2);
        }
    }
}

fn run() {
    // Deep K0 terms recurse deeply; give the evaluator a generous stack so the depth limit,
    // not the host stack, is what bounds it -- the reference maps a host RecursionError to the
    // same `depth_exceeded` trap, and this twin should never need that path.
    let worker = std::thread::Builder::new()
        .stack_size(256 * 1024 * 1024)
        .spawn(serve_stdin)
        .expect("spawn evaluator thread");
    if worker.join().is_err() {
        std::process::exit(1);
    }
}

fn serve_stdin() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        if line.trim().is_empty() {
            continue;
        }
        let response = match k0rs::wire::parse_request(&line) {
            Ok(req) => k0rs::wire::serve(&req),
            Err(e) => k0rs::wire::Response {
                ok: None,
                trap: None,
                error: Some(format!("bad request: {e}")),
                steps: 0,
            },
        };
        let encoded = serde_json::to_string(&response).expect("response serialises");
        if writeln!(out, "{encoded}").is_err() || out.flush().is_err() {
            break;
        }
    }
}
