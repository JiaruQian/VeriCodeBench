use vstd::prelude::*;

verus! {

pub fn option_is_some(o: Option<u64>) -> (r: bool)
    ensures
        r <==> o is Some,
{
    match o { Option::Some(_) => true, Option::None => false }
}

}

fn main() {}
