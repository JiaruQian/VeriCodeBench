use vstd::prelude::*;

verus! {

pub fn result_is_err(res: Result<u64, u64>) -> (r: bool)
    ensures
        r == (res is Err),
{
    match res { Result::Ok(_) => false, Result::Err(_) => true }
}

}

fn main() {}
