use vstd::prelude::*;

verus! {

pub fn double_bounded(x: u64) -> (r: u64)
    requires
        x <= u64::MAX / 2,
    ensures
        r == x * 2,
{
    x * 2
}

}

fn main() {}
