use vstd::prelude::*;

verus! {

pub fn vec_increment_all(v: &mut Vec<u64>)
    requires
        forall|i: int| 0 <= i < old(v).len() ==> old(v)[i] < u64::MAX,
    ensures
        final(v).len() == old(v).len(),
        forall|i: int| 0 <= i < old(v).len() ==> final(v)[i] == old(v)[i] + 1,
{
    let n = v.len();
    let mut i: usize = 0;
    while i < n
        invariant
            n == v.len(),
            v.len() == old(v).len(),
            0 <= i <= n,
            forall|j: int| 0 <= j < old(v).len() ==> old(v)[j] < u64::MAX,
            forall|j: int| 0 <= j < i ==> v[j] == old(v)[j] + 1,
            forall|j: int| i <= j < v.len() ==> v[j] == old(v)[j],
        decreases n - i,
    {
        let x = v[i];
        v.set(i, x + 1);
        i += 1;
    }
}

}

fn main() {}
