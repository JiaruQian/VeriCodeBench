use vstd::prelude::*;

verus! {

pub fn max_u64(x: u64, y: u64) -> (r: u64)
    ensures
        r == x || r == y,
        r >= x && r >= y,
{
    if x >= y { x } else { y }
}

}

fn main() {}
