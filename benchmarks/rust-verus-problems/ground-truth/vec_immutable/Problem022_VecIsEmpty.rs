use vstd::prelude::*;

verus! {

pub fn vec_is_empty(v: &Vec<u64>) -> (r: bool)
    ensures
        r <==> v.len() == 0,
{
    v.len() == 0
}

}

fn main() {}
