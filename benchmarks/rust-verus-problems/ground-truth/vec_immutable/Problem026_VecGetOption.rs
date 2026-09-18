use vstd::prelude::*;

verus! {

pub fn vec_get_option(v: &Vec<u64>, i: usize) -> (r: Option<u64>)
    ensures
        i < v.len() ==> r is Some && r->Some_0 == v[i as int],
        i >= v.len() ==> r is None,
{
    if i < v.len() { Option::Some(v[i]) } else { Option::None }
}

}

fn main() {}
