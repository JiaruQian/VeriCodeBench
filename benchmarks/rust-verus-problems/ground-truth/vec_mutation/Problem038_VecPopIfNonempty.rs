use vstd::prelude::*;

verus! {

pub fn vec_pop_if_nonempty(v: &mut Vec<u64>) -> (r: Option<u64>)
    ensures
        old(v).len() == 0 ==> r is None && final(v)@ == old(v)@,
        old(v).len() > 0 ==> r is Some && r->Some_0 == old(v)[old(v).len() - 1] && final(v)@ == old(v)@.drop_last(),
{
    if v.len() == 0 { Option::None } else { Option::Some(v.pop().unwrap()) }
}

}

fn main() {}
