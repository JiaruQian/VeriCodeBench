/*@
  requires hi >= lo;
  requires hi - lo <= 2147483647;
  assigns \nothing;
  ensures \result == hi - lo;
  ensures \result >= 0;
*/
int nonnegative_diff(int hi, int lo) {
  return hi - lo;
}
