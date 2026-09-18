use vstd::prelude::*;

verus! {

pub fn safe_div_result(x: u64, y: u64) -> (r: Result<u64, ()>)
    ensures
        y == 0 ==> r is Err,
        y != 0 ==> r is Ok && r->Ok_0 == x / y,
{
    if y == 0 { Result::Err(()) } else { Result::Ok(x / y) }
}

}

fn main() {}
