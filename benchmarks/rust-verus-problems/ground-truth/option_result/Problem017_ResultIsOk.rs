use vstd::prelude::*;

verus! {

pub fn result_is_ok(x: Result<u64, ()>) -> (r: bool)
    ensures
        r <==> x is Ok,
{
    match x { Result::Ok(_) => true, Result::Err(_) => false }
}

}

fn main() {}
