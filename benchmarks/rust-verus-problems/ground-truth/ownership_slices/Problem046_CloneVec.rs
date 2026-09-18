use vstd::prelude::*;

verus! {

pub fn clone_vec(v: &Vec<u64>) -> (r: Vec<u64>)
    ensures
        r@ == v@,
{
    v.clone()
}

}

fn main() {}
