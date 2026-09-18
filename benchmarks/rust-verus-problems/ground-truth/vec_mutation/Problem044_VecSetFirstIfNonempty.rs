use vstd::prelude::*;

verus! {

pub fn vec_set_first_if_nonempty(v: &mut Vec<u64>, x: u64) -> (r: bool)
    ensures
        old(v).len() == 0 ==> !r && final(v)@ == old(v)@,
        old(v).len() > 0 ==> r && final(v)@ == old(v)@.update(0, x),
{
    if v.len() == 0 {
        false
    } else {
        v.set(0, x);
        true
    }
}

}

fn main() {}
