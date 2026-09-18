use vstd::prelude::*;

verus! {

pub fn vec_replace_if_in_bounds(v: &mut Vec<u64>, i: usize, x: u64) -> (r: bool)
    ensures
        final(v).len() == old(v).len(),
        i < old(v).len() ==> r && final(v)@ == old(v)@.update(i as int, x),
        i >= old(v).len() ==> !r && final(v)@ == old(v)@,
{
    if i < v.len() {
        v.set(i, x);
        true
    } else {
        false
    }
}

}

fn main() {}
