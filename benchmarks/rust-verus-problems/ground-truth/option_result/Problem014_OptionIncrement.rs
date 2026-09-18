use vstd::prelude::*;

verus! {

pub fn option_increment(o: Option<u64>) -> (r: Option<u64>)
    requires
        o is Some ==> o->Some_0 < u64::MAX,
    ensures
        o is None ==> r is None,
        o is Some ==> r is Some && r->Some_0 == o->Some_0 + 1,
{
    match o { Option::Some(x) => Option::Some(x + 1), Option::None => Option::None }
}

}

fn main() {}
