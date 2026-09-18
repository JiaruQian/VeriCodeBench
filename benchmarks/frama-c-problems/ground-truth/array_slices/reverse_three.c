/*@
  requires n >= 3;
  requires \valid(a + (0..n-1));
  assigns a[0], a[1], a[2];
  ensures a[0] == \old(a[2]) && a[1] == \old(a[1]) && a[2] == \old(a[0]);
  ensures \forall integer j; 3 <= j < n ==> a[j] == \old(a[j]);
*/
void reverse_three(int *a, int n) {
  int t = a[0];
  a[0] = a[2];
  a[2] = t;
}
