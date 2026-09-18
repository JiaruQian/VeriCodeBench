use vstd::prelude::*;

verus! {

pub fn is_odd_u64(x: u64) -> (r: bool)
    ensures
        r == (x % 2 == 1),
{
    x % 2 == 1
}

}

fn main() {}
