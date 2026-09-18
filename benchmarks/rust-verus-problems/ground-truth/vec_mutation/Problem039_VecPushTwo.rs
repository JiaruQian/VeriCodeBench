use vstd::prelude::*;

verus! {

pub fn vec_push_two(v: &mut Vec<u64>, x: u64, y: u64)
    ensures
        final(v)@ == old(v)@.push(x).push(y),
{
    v.push(x);
    v.push(y);
}

}

fn main() {}
