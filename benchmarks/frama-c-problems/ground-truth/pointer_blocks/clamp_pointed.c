/*@
  requires \valid(x);
  requires lo <= hi;
  assigns *x;
  ensures lo <= *x && *x <= hi;
  ensures \old(*x) < lo ==> *x == lo;
  ensures \old(*x) > hi ==> *x == hi;
  ensures lo <= \old(*x) <= hi ==> *x == \old(*x);
*/
void clamp_pointed(int *x, int lo, int hi) {
  if (*x < lo) {
    *x = lo;
  } else if (*x > hi) {
    *x = hi;
  }
}
