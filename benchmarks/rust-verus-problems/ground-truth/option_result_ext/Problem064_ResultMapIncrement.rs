use vstd::prelude::*;

verus! {

pub fn result_map_increment(res: Result<u64, u64>) -> (r: Result<u64, u64>)
    requires
        res is Ok ==> res->Ok_0 < u64::MAX,
    ensures
        res is Ok ==> r is Ok && r->Ok_0 == res->Ok_0 + 1,
        res is Err ==> r is Err && r->Err_0 == res->Err_0,
{
    match res { Result::Ok(x) => Result::Ok(x + 1), Result::Err(e) => Result::Err(e) }
}

}

fn main() {}
