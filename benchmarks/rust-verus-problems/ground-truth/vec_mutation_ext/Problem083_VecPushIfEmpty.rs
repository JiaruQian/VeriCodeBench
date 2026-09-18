use vstd::prelude::*;

verus! {

pub fn vec_push_if_empty(v: &mut Vec<u64>, x: u64)
    ensures
        old(v).len() == 0 ==> final(v)@ == old(v)@.push(x),
        old(v).len() != 0 ==> final(v)@ == old(v)@,
{
    if v.len() == 0 { v.push(x); }
}

}

fn main() {}
