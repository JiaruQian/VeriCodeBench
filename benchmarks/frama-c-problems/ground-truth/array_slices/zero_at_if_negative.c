/*@
  requires n > 0 && 0 <= idx < n;
  requires \valid(a + (0..n-1));
  assigns a[idx];
  ensures \old(a[idx]) < 0 ==> a[idx] == 0;
  ensures \old(a[idx]) >= 0 ==> a[idx] == \old(a[idx]);
*/
void zero_at_if_negative(int *a, int n, int idx) {
  if (a[idx] < 0) {
    a[idx] = 0;
  }
}
