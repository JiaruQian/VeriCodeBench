use vstd::prelude::*;

verus! {

pub fn result_default(res: Result<u64, u64>, default: u64) -> (r: u64)
    ensures
        res is Ok ==> r == res->Ok_0,
        res is Err ==> r == default,
{
    match res { Result::Ok(x) => x, Result::Err(_) => default }
}

}

fn main() {}
