use vstd::prelude::*;

verus! {

pub fn vec_set_second(v: &mut Vec<u64>, x: u64)
    requires
        old(v).len() >= 2,
    ensures
        final(v)@ == old(v)@.update(1, x),
{
    v.set(1, x);
}

}

fn main() {}
