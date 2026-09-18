/*@
  requires n >= 0;
  requires \valid_read(a + (0..n-1));
  requires \forall integer j; 0 <= j < n ==> a[j] >= 0;
  assigns \nothing;
  ensures \result >= 0;
*/
int array_sum_nonnegative(int const *a, int n) {
  int s = 0;
  /*@
    loop invariant 0 <= i <= n;
    loop invariant s >= 0;
    loop assigns i, s;
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    s = s + a[i];
  }
  return s;
}
