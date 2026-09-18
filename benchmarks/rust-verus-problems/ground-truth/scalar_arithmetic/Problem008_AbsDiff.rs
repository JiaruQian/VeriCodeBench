use vstd::prelude::*;

verus! {

pub fn abs_diff_u64(x: u64, y: u64) -> (r: u64)
    ensures
        x >= y ==> r == x - y,
        x < y ==> r == y - x,
{
    if x >= y { x - y } else { y - x }
}

}

fn main() {}
