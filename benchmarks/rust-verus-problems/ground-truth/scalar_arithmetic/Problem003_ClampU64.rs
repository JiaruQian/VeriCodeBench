use vstd::prelude::*;

verus! {

pub fn clamp_u64(x: u64, lo: u64, hi: u64) -> (r: u64)
    requires
        lo <= hi,
    ensures
        lo <= r && r <= hi,
        x < lo ==> r == lo,
        lo <= x && x <= hi ==> r == x,
        x > hi ==> r == hi,
{
    if x < lo { lo } else if x > hi { hi } else { x }
}

}

fn main() {}
