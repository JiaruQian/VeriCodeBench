use vstd::prelude::*;

verus! {

pub fn option_filter_even(o: Option<u64>) -> (r: Option<u64>)
    ensures
        o is Some && o->Some_0 % 2 == 0 ==> r is Some && r->Some_0 == o->Some_0,
        o is None ==> r is None,
        o is Some && o->Some_0 % 2 == 1 ==> r is None,
{
    match o {
        Option::Some(x) => if x % 2 == 0 { Option::Some(x) } else { Option::None },
        Option::None => Option::None,
    }
}

}

fn main() {}
