use vstd::prelude::*;

verus! {

pub fn slice_len(s: &[u64]) -> (r: usize)
    ensures
        r == s.len(),
        r == s@.len(),
{
    s.len()
}

}

fn main() {}
