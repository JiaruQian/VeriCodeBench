use vstd::prelude::*;

verus! {

pub fn vec_last_or_default(v: &Vec<u64>, default: u64) -> (r: u64)
    ensures
        v.len() > 0 ==> r == v[v.len() - 1],
        v.len() == 0 ==> r == default,
{
    if v.len() > 0 { v[v.len() - 1] } else { default }
}

}

fn main() {}
