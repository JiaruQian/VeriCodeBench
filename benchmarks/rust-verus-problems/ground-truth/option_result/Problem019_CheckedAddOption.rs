use vstd::prelude::*;

verus! {

pub fn checked_add_option(x: u64, y: u64) -> (r: Option<u64>)
    ensures
        x <= u64::MAX - y ==> r is Some && r->Some_0 == x + y,
        x > u64::MAX - y ==> r is None,
{
    if x <= u64::MAX - y { Option::Some(x + y) } else { Option::None }
}

}

fn main() {}
