use vstd::prelude::*;

verus! {

pub fn vec_third(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() > 2,
    ensures
        r == v[2],
{
    v[2]
}

}

fn main() {}
