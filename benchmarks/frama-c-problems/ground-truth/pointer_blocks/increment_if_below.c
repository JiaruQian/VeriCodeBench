/*@
  requires \valid(x);
  requires *x < limit ==> *x < 2147483647;
  assigns *x;
  ensures \old(*x) < limit ==> *x == \old(*x) + 1;
  ensures \old(*x) >= limit ==> *x == \old(*x);
*/
void increment_if_below(int *x, int limit) {
  if (*x < limit) {
    *x = *x + 1;
  }
}
