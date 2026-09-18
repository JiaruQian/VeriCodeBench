use vstd::prelude::*;

verus! {

pub fn array_sum3_bounded(a: &[u64; 3]) -> (r: u64)
    requires
        a@[0] <= u64::MAX - a@[1],
        a@[0] + a@[1] <= u64::MAX - a@[2],
    ensures
        r == a@[0] + a@[1] + a@[2],
{
    a[0] + a[1] + a[2]
}

}

fn main() {}
