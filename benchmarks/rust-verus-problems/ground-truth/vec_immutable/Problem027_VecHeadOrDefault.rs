use vstd::prelude::*;

verus! {

pub fn vec_head_or_default(v: &Vec<u64>, default: u64) -> (r: u64)
    ensures
        v.len() > 0 ==> r == v[0],
        v.len() == 0 ==> r == default,
{
    if v.len() > 0 { v[0] } else { default }
}

}

fn main() {}
