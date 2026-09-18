use vstd::prelude::*;

verus! {

pub fn option_is_zero(o: Option<u64>) -> (r: bool)
    ensures
        r == (o is Some && o->Some_0 == 0),
{
    match o { Option::Some(x) => x == 0, Option::None => false }
}

}

fn main() {}
