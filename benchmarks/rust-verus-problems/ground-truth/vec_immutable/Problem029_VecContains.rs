use vstd::prelude::*;

verus! {

pub fn vec_contains(v: &Vec<u64>, target: u64) -> (r: bool)
    ensures
        r <==> exists|i: int| 0 <= i < v.len() && v[i] == target,
{
    let mut i: usize = 0;
    while i < v.len()
        invariant
            0 <= i <= v.len(),
            forall|j: int| 0 <= j < i ==> v[j] != target,
        decreases v.len() - i,
    {
        if v[i] == target { return true; }
        i += 1;
    }
    false
}

}

fn main() {}
