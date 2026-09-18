use vstd::prelude::*;

verus! {

pub fn option_is_none(o: Option<u64>) -> (r: bool)
    ensures
        r <==> o is None,
{
    match o { Option::Some(_) => false, Option::None => true }
}

}

fn main() {}
