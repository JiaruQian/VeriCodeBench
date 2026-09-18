use vstd::prelude::*;

verus! {

pub fn decrement_positive(x: u64) -> (r: u64)
    requires
        x > 0,
    ensures
        r == x - 1,
{
    x - 1
}

}

fn main() {}
