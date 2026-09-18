use vstd::prelude::*;

verus! {

pub fn unwrap_or_u64(o: Option<u64>, default: u64) -> (r: u64)
    ensures
        o is Some ==> r == o->Some_0,
        o is None ==> r == default,
{
    match o { Option::Some(x) => x, Option::None => default }
}

}

fn main() {}
