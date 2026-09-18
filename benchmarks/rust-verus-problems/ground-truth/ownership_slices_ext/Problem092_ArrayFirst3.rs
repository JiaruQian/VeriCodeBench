use vstd::prelude::*;

verus! {

pub fn array_first3(a: &[u64; 3]) -> (r: u64)
    ensures
        r == a@[0],
{
    a[0]
}

}

fn main() {}
