use vstd::prelude::*;

verus! {

pub fn vec_get_at(v: &Vec<u64>, i: usize) -> (r: u64)
    requires
        i < v.len(),
    ensures
        r == v[i as int],
{
    v[i]
}

}

fn main() {}
