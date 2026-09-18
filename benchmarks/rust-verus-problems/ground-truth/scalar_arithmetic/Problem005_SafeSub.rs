use vstd::prelude::*;

verus! {

pub fn safe_sub(x: u64, y: u64) -> (r: u64)
    requires
        y <= x,
    ensures
        r == x - y,
{
    x - y
}

}

fn main() {}
