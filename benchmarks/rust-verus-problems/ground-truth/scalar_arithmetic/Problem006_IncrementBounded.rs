use vstd::prelude::*;

verus! {

pub fn increment_bounded(x: u64) -> (r: u64)
    requires
        x < u64::MAX,
    ensures
        r == x + 1,
{
    x + 1
}

}

fn main() {}
