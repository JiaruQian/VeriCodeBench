use vstd::prelude::*;

verus! {

pub fn vec_swap_first_last(v: &mut Vec<u64>)
    requires
        old(v).len() > 0,
    ensures
        final(v).len() == old(v).len(),
        final(v)[0] == old(v)[(old(v).len() - 1) as int],
        final(v)[(old(v).len() - 1) as int] == old(v)[0],
{
    let last = v.len() - 1;
    let first_value = v[0];
    let last_value = v[last];
    v.set(0, last_value);
    v.set(last, first_value);
}

}

fn main() {}
