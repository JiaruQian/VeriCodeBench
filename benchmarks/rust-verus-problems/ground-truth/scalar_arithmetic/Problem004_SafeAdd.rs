use vstd::prelude::*;

verus! {

pub fn safe_add(x: u64, y: u64) -> (r: u64)
    requires
        x <= u64::MAX - y,
    ensures
        r == x + y,
{
    x + y
}

}

fn main() {}
