use vstd::prelude::*;

verus! {

pub fn take_vec_len(v: Vec<u64>) -> (r: usize)
    ensures
        r == v@.len(),
{
    v.len()
}

}

fn main() {}
