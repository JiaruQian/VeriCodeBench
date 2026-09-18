use vstd::prelude::*;

verus! {

pub fn vec_pair_sorted(v: &Vec<u64>) -> (r: bool)
    requires
        v.len() == 2,
    ensures
        r == (v[0] <= v[1]),
{
    v[0] <= v[1]
}

}

fn main() {}
