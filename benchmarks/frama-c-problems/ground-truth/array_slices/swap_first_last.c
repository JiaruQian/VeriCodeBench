/*@
  requires n >= 2;
  requires \valid(a + (0..n-1));
  assigns a[0], a[n-1];
  ensures a[0] == \old(a[n-1]);
  ensures a[n-1] == \old(a[0]);
  ensures \forall integer j; 1 <= j < n-1 ==> a[j] == \old(a[j]);
*/
void swap_first_last(int *a, int n) {
  int t = a[0];
  a[0] = a[n - 1];
  a[n - 1] = t;
}
