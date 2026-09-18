use vstd::prelude::*;

verus! {

pub fn saturating_sub_u64(x: u64, y: u64) -> (r: u64)
    ensures
        x >= y ==> r == x - y,
        x < y ==> r == 0,
{
    if x >= y { x - y } else { 0 }
}

}

fn main() {}
