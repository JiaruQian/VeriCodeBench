use vstd::prelude::*;

verus! {

pub fn vec_fill_all(v: &mut Vec<u64>, x: u64)
    ensures
        final(v).len() == old(v).len(),
        forall|i: int| 0 <= i < old(v).len() ==> final(v)[i] == x,
{
    let n = v.len();
    let mut i: usize = 0;
    while i < n
        invariant
            n == v.len(),
            0 <= i <= n,
            forall|j: int| 0 <= j < i ==> v[j] == x,
        decreases n - i,
    {
        v.set(i, x);
        i += 1;
    }
}

}

fn main() {}
