use vstd::prelude::*;

verus! {

pub fn filter_nonzero(x: u64) -> (r: Option<u64>)
    ensures
        x == 0 ==> r is None,
        x != 0 ==> r is Some && r->Some_0 == x,
{
    if x == 0 { Option::None } else { Option::Some(x) }
}

}

fn main() {}
