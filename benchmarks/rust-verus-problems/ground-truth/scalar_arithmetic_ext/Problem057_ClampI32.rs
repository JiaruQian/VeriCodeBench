use vstd::prelude::*;

verus! {

pub fn clamp_i32(x: i32, low: i32, high: i32) -> (r: i32)
    requires
        low <= high,
    ensures
        low <= r && r <= high,
        low <= x && x <= high ==> r == x,
        x < low ==> r == low,
        x > high ==> r == high,
{
    if x < low { low } else if x > high { high } else { x }
}

}

fn main() {}
