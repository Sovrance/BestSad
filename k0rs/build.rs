//! Build-time check: the twin's kernel descriptor hashes to the Python `KERNEL_VERSION_HASH`.
//!
//! ADR-0020: "The twin's KERNEL_VERSION_HASH must be computed from the same descriptor and
//! must equal the Python constant; a mismatch is a build failure." The descriptor module is
//! compiled into the build script directly so the check runs before any twin code exists.

#[path = "src/descriptor.rs"]
mod descriptor;

fn main() {
    println!("cargo:rerun-if-changed=src/descriptor.rs");
    println!("cargo:rerun-if-changed=build.rs");
    let actual = descriptor::kernel_version_hash();
    if actual != descriptor::PYTHON_KERNEL_VERSION_HASH {
        panic!(
            "\n\nK0 twin descriptor does not match the Python reference.\n  twin   : {actual}\n  python : {}\n\
             The Python reference is normative (ADR-0002). Fix src/descriptor.rs; never the pin.\n",
            descriptor::PYTHON_KERNEL_VERSION_HASH
        );
    }
}
