use vstd::prelude::*;

verus! {

pub fn vec_get_or_zero(v: &Vec<u64>, i: usize) -> (r: u64)
    ensures
        i < v.len() ==> r == v[i as int],
        i >= v.len() ==> r == 0,
{
    if i < v.len() { v[i] } else { 0 }
}

}

fn main() {}
