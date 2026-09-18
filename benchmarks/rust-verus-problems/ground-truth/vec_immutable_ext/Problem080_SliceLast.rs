use vstd::prelude::*;

verus! {

pub fn slice_last(s: &[u64]) -> (r: u64)
    requires
        s.len() > 0,
    ensures
        r == s[(s.len() - 1) as int],
{
    s[s.len() - 1]
}

}

fn main() {}
