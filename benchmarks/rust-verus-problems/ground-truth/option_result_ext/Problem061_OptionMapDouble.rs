use vstd::prelude::*;

verus! {

pub fn option_map_double(o: Option<u64>) -> (r: Option<u64>)
    requires
        o is Some ==> o->Some_0 <= u64::MAX / 2,
    ensures
        o is None ==> r is None,
        o is Some ==> r is Some && r->Some_0 == o->Some_0 * 2,
{
    match o {
        Option::Some(x) => Option::Some(x * 2),
        Option::None => Option::None,
    }
}

}

fn main() {}
