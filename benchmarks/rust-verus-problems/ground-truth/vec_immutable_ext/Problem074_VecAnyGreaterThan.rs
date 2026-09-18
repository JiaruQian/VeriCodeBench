use vstd::prelude::*;

verus! {

pub fn vec_any_greater_than(v: &Vec<u64>, limit: u64) -> (r: bool)
    ensures
        r == (exists|i: int| 0 <= i < v.len() && v[i] > limit),
{
    let mut i: usize = 0;
    while i < v.len()
        invariant
            0 <= i <= v.len(),
            forall|j: int| 0 <= j < i ==> v[j] <= limit,
        decreases v.len() - i,
    {
        if v[i] > limit {
            return true;
        }
        i += 1;
    }
    false
}

}

fn main() {}
