use vstd::prelude::*;

verus! {

pub fn vec_swap_two(v: &mut Vec<u64>, i: usize, j: usize)
    requires
        i < old(v).len(),
        j < old(v).len(),
    ensures
        final(v).len() == old(v).len(),
        final(v)[i as int] == old(v)[j as int],
        final(v)[j as int] == old(v)[i as int],
        forall|k: int| 0 <= k < old(v).len() && k != i && k != j ==> final(v)[k] == old(v)[k],
{
    let x = v[i];
    let y = v[j];
    v.set(i, y);
    v.set(j, x);
}

}

fn main() {}
