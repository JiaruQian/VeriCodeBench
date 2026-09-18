use vstd::prelude::*;

verus! {

pub fn vec_len_at_least(v: &Vec<u64>, n: usize) -> (r: bool)
    ensures
        r == (v.len() >= n),
{
    v.len() >= n
}

}

fn main() {}
