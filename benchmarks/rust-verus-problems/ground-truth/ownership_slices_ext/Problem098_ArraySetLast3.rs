use vstd::prelude::*;

verus! {

pub fn array_set_last3(a: &mut [u64; 3], x: u64)
    ensures
        final(a)@ == old(a)@.update(2, x),
{
    a[2] = x;
}

}

fn main() {}
