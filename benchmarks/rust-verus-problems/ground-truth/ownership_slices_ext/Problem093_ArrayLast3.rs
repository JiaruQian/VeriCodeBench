use vstd::prelude::*;

verus! {

pub fn array_last3(a: &[u64; 3]) -> (r: u64)
    ensures
        r == a@[2],
{
    a[2]
}

}

fn main() {}
