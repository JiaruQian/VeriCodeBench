/*@
  requires lo <= hi;
  assigns \nothing;
  ensures lo <= \result <= hi;
  ensures x < lo ==> \result == lo;
  ensures x > hi ==> \result == hi;
  ensures lo <= x <= hi ==> \result == x;
*/
int clamp_int(int x, int lo, int hi) {
  if (x < lo) {
    return lo;
  }
  if (x > hi) {
    return hi;
  }
  return x;
}
