use vstd::prelude::*;

verus! {

#[verifier(nonlinear)]
pub fn safe_mul_u64(x: u64, y: u64) -> (r: u64)
    requires
        y == 0 || x <= u64::MAX / y,
    ensures
        r == x * y,
{
    x * y
}

}

fn main() {}
