/*@
  requires n >= 0;
  requires \valid_read(a + (0..n-1));
  assigns \nothing;
  ensures \result == 1 ==> \forall integer j; 0 <= j < n ==> a[j] == 0;
  ensures \result == 0 ==> \exists integer j; 0 <= j < n && a[j] != 0;
*/
int is_all_zero(int const *a, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> a[j] == 0;
    loop assigns i;
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (a[i] != 0) {
      return 0;
    }
  }
  return 1;
}
