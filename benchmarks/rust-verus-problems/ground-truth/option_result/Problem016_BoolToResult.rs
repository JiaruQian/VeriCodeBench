use vstd::prelude::*;

verus! {

pub fn bool_to_result(ok: bool, value: u64) -> (r: Result<u64, ()>)
    ensures
        ok ==> r is Ok && r->Ok_0 == value,
        !ok ==> r is Err,
{
    if ok { Result::Ok(value) } else { Result::Err(()) }
}

}

fn main() {}
