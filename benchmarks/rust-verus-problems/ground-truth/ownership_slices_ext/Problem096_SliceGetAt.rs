use vstd::prelude::*;

verus! {

pub fn slice_get_at(s: &[u64], i: usize) -> (r: u64)
    requires
        i < s.len(),
    ensures
        r == s[i as int],
{
    s[i]
}

}

fn main() {}
