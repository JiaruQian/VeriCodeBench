use vstd::prelude::*;

verus! {

pub fn vec_set_all_zero(v: &mut Vec<u64>)
    ensures
        final(v).len() == old(v).len(),
        forall|i: int| 0 <= i < old(v).len() ==> final(v)[i] == 0,
{
    let n = v.len();
    let mut i: usize = 0;
    while i < n
        invariant
            n == v.len(),
            0 <= i <= n,
            forall|j: int| 0 <= j < i ==> v[j] == 0,
        decreases n - i,
    {
        v.set(i, 0);
        i += 1;
    }
}

}

fn main() {}
