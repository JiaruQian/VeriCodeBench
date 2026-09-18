use vstd::prelude::*;

verus! {

pub fn array_set3(a: &mut [u64; 3], i: usize, x: u64)
    requires
        i < 3,
    ensures
        final(a)@ == old(a)@.update(i as int, x),
{
    a[i] = x;
}

}

fn main() {}
