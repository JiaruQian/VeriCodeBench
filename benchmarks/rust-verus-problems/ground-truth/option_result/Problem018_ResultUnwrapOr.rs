use vstd::prelude::*;

verus! {

pub fn result_unwrap_or(x: Result<u64, ()>, default: u64) -> (r: u64)
    ensures
        x is Ok ==> r == x->Ok_0,
        x is Err ==> r == default,
{
    match x { Result::Ok(v) => v, Result::Err(_) => default }
}

}

fn main() {}
