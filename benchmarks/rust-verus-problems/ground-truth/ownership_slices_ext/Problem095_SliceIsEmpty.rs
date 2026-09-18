use vstd::prelude::*;

verus! {

pub fn slice_is_empty(s: &[u64]) -> (r: bool)
    ensures
        r == (s.len() == 0),
{
    s.len() == 0
}

}

fn main() {}
