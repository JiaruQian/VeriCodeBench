use vstd::prelude::*;

verus! {

pub fn array_get3(a: &[u64; 3], i: usize) -> (r: u64)
    requires
        i < 3,
    ensures
        r == a@[i as int],
{
    a[i]
}

}

fn main() {}
