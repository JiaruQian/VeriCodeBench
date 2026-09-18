use vstd::prelude::*;

verus! {

pub fn array_swap3(a: &mut [u64; 3], i: usize, j: usize)
    requires
        i < 3 && j < 3,
    ensures
        final(a)@[i as int] == old(a)@[j as int],
        final(a)@[j as int] == old(a)@[i as int],
{
    let xi = a[i];
    let xj = a[j];
    a[i] = xj;
    a[j] = xi;
}

}

fn main() {}
