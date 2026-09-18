use vstd::prelude::*;

verus! {

pub fn vec_same_len(a: &Vec<u64>, b: &Vec<u64>) -> (r: bool)
    ensures
        r == (a.len() == b.len()),
{
    a.len() == b.len()
}

}

fn main() {}
