/*@
  requires n >= 0;
  requires \valid(a + (0..n-1));
  assigns a[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> a[j] == 0;
*/
void fill_zero(int *a, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> a[j] == 0;
    loop assigns i, a[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    a[i] = 0;
  }
}
