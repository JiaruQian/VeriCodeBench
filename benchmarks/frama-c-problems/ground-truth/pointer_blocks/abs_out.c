/*@
  requires x > -2147483648;
  requires \valid(out);
  assigns *out;
  ensures *out >= 0;
  ensures x >= 0 ==> *out == x;
  ensures x < 0 ==> *out == -x;
*/
void abs_out(int x, int *out) {
  if (x < 0) {
    *out = -x;
  } else {
    *out = x;
  }
}
