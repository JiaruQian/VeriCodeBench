/*@
  requires n >= 0;
  assigns \nothing;
  ensures \result == n;
*/
int count_up_to_n(int n) {
  int i = 0;
  /*@
    loop invariant 0 <= i <= n;
    loop assigns i;
    loop variant n - i;
  */
  while (i < n) {
    i = i + 1;
  }
  return i;
}
