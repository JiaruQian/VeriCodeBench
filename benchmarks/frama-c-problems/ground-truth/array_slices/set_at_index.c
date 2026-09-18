/*@
  requires n > 0 && 0 <= idx < n;
  requires \valid(a + (0..n-1));
  assigns a[idx];
  ensures a[idx] == value;
  ensures \forall integer j; 0 <= j < n && j != idx ==> a[j] == \old(a[j]);
*/
void set_at_index(int *a, int n, int idx, int value) {
  a[idx] = value;
}
