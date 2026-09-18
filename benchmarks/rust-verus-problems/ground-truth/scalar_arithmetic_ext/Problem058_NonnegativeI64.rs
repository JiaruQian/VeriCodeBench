use vstd::prelude::*;

verus! {

pub fn is_nonnegative_i64(x: i64) -> (r: bool)
    ensures
        r == (x >= 0),
{
    x >= 0
}

}

fn main() {}
