use vstd::prelude::*;

verus! {

pub fn option_or_u64(a: Option<u64>, b: Option<u64>) -> (r: Option<u64>)
    ensures
        a is Some ==> r == a,
        a is None ==> r == b,
{
    match a { Option::Some(x) => Option::Some(x), Option::None => b }
}

}

fn main() {}
