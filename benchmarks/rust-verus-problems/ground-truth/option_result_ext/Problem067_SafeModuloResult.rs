use vstd::prelude::*;

verus! {

pub fn safe_mod_result(x: u64, y: u64) -> (r: Result<u64, u64>)
    ensures
        y != 0 ==> r is Ok && r->Ok_0 == x % y,
        y == 0 ==> r is Err && r->Err_0 == x,
{
    if y == 0 { Result::Err(x) } else { Result::Ok(x % y) }
}

}

fn main() {}
