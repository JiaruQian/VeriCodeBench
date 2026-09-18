use vstd::prelude::*;

verus! {

pub fn array_all_zero3(a: &[u64; 3]) -> (r: bool)
    ensures
        r == (a@[0] == 0 && a@[1] == 0 && a@[2] == 0),
{
    a[0] == 0 && a[1] == 0 && a[2] == 0
}

}

fn main() {}
