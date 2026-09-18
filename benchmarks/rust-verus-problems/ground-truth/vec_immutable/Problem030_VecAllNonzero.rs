use vstd::prelude::*;

verus! {

pub fn vec_all_nonzero(v: &Vec<u64>) -> (r: bool)
    ensures
        r <==> forall|i: int| 0 <= i < v.len() ==> v[i] != 0,
{
    let mut i: usize = 0;
    while i < v.len()
        invariant
            0 <= i <= v.len(),
            forall|j: int| 0 <= j < i ==> v[j] != 0,
        decreases v.len() - i,
    {
        if v[i] == 0 { return false; }
        i += 1;
    }
    true
}

}

fn main() {}
