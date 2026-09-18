use vstd::prelude::*;

verus! {

pub fn vec_pop_if_len_gt_one(v: &mut Vec<u64>)
    ensures
        old(v).len() > 1 ==> final(v)@ == old(v)@.subrange(0, old(v).len() - 1),
        old(v).len() <= 1 ==> final(v)@ == old(v)@,
{
    if v.len() > 1 { v.pop(); }
}

}

fn main() {}
