use vstd::prelude::*;

verus! {

pub fn checked_sub_option(x: u64, y: u64) -> (r: Option<u64>)
    ensures
        x >= y ==> r is Some && r->Some_0 == x - y,
        x < y ==> r is None,
{
    if x >= y { Option::Some(x - y) } else { Option::None }
}

}

fn main() {}
