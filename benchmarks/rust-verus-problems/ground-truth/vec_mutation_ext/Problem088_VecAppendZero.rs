use vstd::prelude::*;

verus! {

pub fn vec_append_zero(v: &mut Vec<u64>)
    ensures
        final(v)@ == old(v)@.push(0),
{
    v.push(0);
}

}

fn main() {}
