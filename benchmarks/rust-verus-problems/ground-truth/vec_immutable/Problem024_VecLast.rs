use vstd::prelude::*;

verus! {

pub fn vec_last(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() > 0,
    ensures
        r == v[v.len() - 1],
{
    v[v.len() - 1]
}

}

fn main() {}
