use vstd::prelude::*;

verus! {

pub fn is_even_u64(x: u64) -> (r: bool)
    ensures
        r == (x % 2 == 0),
{
    x % 2 == 0
}

}

fn main() {}
