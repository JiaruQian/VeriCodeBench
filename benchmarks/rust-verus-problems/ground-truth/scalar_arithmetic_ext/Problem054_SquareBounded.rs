use vstd::prelude::*;

verus! {

#[verifier(nonlinear)]
pub fn square_bounded(x: u64) -> (r: u64)
    requires
        x <= 4294967295,
    ensures
        r == x * x,
{
    x * x
}

}

fn main() {}
