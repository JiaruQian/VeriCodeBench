use vstd::prelude::*;

verus! {

pub fn vec_push_value(v: &mut Vec<u64>, x: u64)
    ensures
        final(v)@ == old(v)@.push(x),
{
    v.push(x);
}

}

fn main() {}
