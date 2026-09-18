use vstd::prelude::*;

verus! {

pub fn vec_set_at(v: &mut Vec<u64>, i: usize, x: u64)
    requires
        i < old(v).len(),
    ensures
        final(v)@ == old(v)@.update(i as int, x),
{
    v.set(i, x);
}

}

fn main() {}
