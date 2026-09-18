use vstd::prelude::*;

verus! {

pub fn vec_truncate_one(v: &mut Vec<u64>)
    ensures
        old(v).len() == 0 ==> final(v).len() == 0,
        old(v).len() > 0 ==> final(v).len() == 1,
        old(v).len() > 0 ==> final(v)[0] == old(v)[0],
{
    while v.len() > 1
        invariant
            v.len() <= old(v).len(),
            old(v).len() == 0 ==> v.len() == 0,
            old(v).len() > 0 ==> v.len() > 0,
            old(v).len() > 0 ==> v[0] == old(v)[0],
        decreases v.len(),
    {
        v.pop();
    }
}

}

fn main() {}
