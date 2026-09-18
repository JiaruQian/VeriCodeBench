use vstd::prelude::*;

verus! {

pub fn array_set_first3(a: &mut [u64; 3], x: u64)
    ensures
        final(a)@ == old(a)@.update(0, x),
{
    a[0] = x;
}

}

fn main() {}
