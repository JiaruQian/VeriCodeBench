use vstd::prelude::*;

verus! {

pub fn vec_clear_all(v: &mut Vec<u64>)
    ensures
        final(v).len() == 0,
{
    while v.len() > 0
        invariant
            v.len() >= 0,
        decreases v.len(),
    {
        v.pop();
    }
}

}

fn main() {}
