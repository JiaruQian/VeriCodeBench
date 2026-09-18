/*@
  requires n >= 0;
  requires \valid(a + (0..n-1));
  requires \forall integer j; 0 <= j < n ==> a[j] < 2147483647;
  assigns a[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> a[j] == \old(a[j]) + 1;
*/
void increment_all_bounded(int *a, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> a[j] == \at(a[j],Pre) + 1;
    loop invariant \forall integer j; i <= j < n ==> a[j] == \at(a[j],Pre);
    loop assigns i, a[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    a[i] = a[i] + 1;
  }
}
