use vstd::prelude::*;

verus! {

pub fn vec_increment_first(v: &mut Vec<u64>)
    requires
        old(v).len() > 0,
        old(v)[0] < u64::MAX,
    ensures
        final(v).len() == old(v).len(),
        final(v)[0] == old(v)[0] + 1,
{
    let x = v[0];
    v.set(0, x + 1);
}

}

fn main() {}
