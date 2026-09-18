use vstd::prelude::*;

verus! {

pub fn slice_first(s: &[u64]) -> (r: u64)
    requires
        s.len() > 0,
    ensures
        r == s[0],
{
    s[0]
}

}

fn main() {}
