use vstd::prelude::*;

verus! {

pub fn vec_sum2(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() == 2,
        v[0] <= u64::MAX - v[1],
    ensures
        r == v[0] + v[1],
{
    v[0] + v[1]
}

}

fn main() {}
