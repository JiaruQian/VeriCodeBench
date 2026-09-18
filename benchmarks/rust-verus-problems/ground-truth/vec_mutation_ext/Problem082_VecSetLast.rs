use vstd::prelude::*;

verus! {

pub fn vec_set_last(v: &mut Vec<u64>, x: u64)
    requires
        old(v).len() > 0,
    ensures
        final(v).len() == old(v).len(),
        final(v)@ == old(v)@.update((old(v).len() - 1) as int, x),
{
    let i = v.len() - 1;
    v.set(i, x);
}

}

fn main() {}
