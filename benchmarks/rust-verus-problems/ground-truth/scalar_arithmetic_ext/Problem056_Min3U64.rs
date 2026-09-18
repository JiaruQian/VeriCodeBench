use vstd::prelude::*;

verus! {

pub fn min3_u64(x: u64, y: u64, z: u64) -> (r: u64)
    ensures
        r == x || r == y || r == z,
        r <= x && r <= y && r <= z,
{
    let m = if x <= y { x } else { y };
    if m <= z { m } else { z }
}

}

fn main() {}
