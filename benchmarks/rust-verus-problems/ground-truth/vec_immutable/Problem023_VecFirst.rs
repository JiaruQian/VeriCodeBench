use vstd::prelude::*;

verus! {

pub fn vec_first(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() > 0,
    ensures
        r == v[0],
{
    v[0]
}

}

fn main() {}
