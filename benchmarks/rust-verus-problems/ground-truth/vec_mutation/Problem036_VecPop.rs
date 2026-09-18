use vstd::prelude::*;

verus! {

pub fn vec_pop_value(v: &mut Vec<u64>) -> (r: u64)
    requires
        old(v).len() > 0,
    ensures
        r == old(v)[old(v).len() - 1],
        final(v)@ == old(v)@.drop_last(),
{
    v.pop().unwrap()
}

}

fn main() {}
