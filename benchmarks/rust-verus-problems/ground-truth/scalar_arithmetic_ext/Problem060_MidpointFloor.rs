use vstd::prelude::*;

verus! {

pub fn midpoint_floor(x: u64, y: u64) -> (r: u64)
    requires
        x <= u64::MAX - y,
    ensures
        r == (x + y) / 2,
{
    (x + y) / 2
}

}

fn main() {}
