use vstd::prelude::*;

verus! {

pub fn vec_all_less_than(v: &Vec<u64>, limit: u64) -> (r: bool)
    ensures
        r == (forall|i: int| 0 <= i < v.len() ==> v[i] < limit),
{
    let mut i: usize = 0;
    while i < v.len()
        invariant
            0 <= i <= v.len(),
            forall|j: int| 0 <= j < i ==> v[j] < limit,
        decreases v.len() - i,
    {
        if v[i] >= limit {
            return false;
        }
        i += 1;
    }
    true
}

}

fn main() {}
