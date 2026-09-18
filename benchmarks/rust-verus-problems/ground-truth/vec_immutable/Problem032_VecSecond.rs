use vstd::prelude::*;

verus! {

pub fn vec_second(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() > 1,
    ensures
        r == v[1],
{
    v[1]
}

}

fn main() {}
