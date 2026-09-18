use vstd::prelude::*;

verus! {

pub fn option_default_zero(o: Option<u64>) -> (r: u64)
    ensures
        o is Some ==> r == o->Some_0,
        o is None ==> r == 0,
{
    match o { Option::Some(x) => x, Option::None => 0 }
}

}

fn main() {}
