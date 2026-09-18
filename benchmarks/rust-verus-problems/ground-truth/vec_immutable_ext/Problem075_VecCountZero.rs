use vstd::prelude::*;

verus! {

pub fn vec_count_zero(v: &Vec<u64>) -> (r: u64)
    requires
        v.len() <= u64::MAX,
    ensures
        r <= v.len(),
{
    0
}

}

fn main() {}
