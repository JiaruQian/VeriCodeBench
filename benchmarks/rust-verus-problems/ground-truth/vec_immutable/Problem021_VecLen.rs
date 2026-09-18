use vstd::prelude::*;

verus! {

pub fn vec_len(v: &Vec<u64>) -> (r: usize)
    ensures
        r == v.len(),
        r == v@.len(),
{
    v.len()
}

}

fn main() {}
