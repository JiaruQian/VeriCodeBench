/*@
  requires n >= 0;
  requires \valid(a + (0..n-1));
  assigns a[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> a[j] >= 0;
  ensures \forall integer j; 0 <= j < n && \old(a[j]) >= 0 ==> a[j] == \old(a[j]);
  ensures \forall integer j; 0 <= j < n && \old(a[j]) < 0 ==> a[j] == 0;
*/
void replace_negative_with_zero(int *a, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> a[j] >= 0;
    loop invariant \forall integer j; 0 <= j < i && \at(a[j],Pre) >= 0 ==> a[j] == \at(a[j],Pre);
    loop invariant \forall integer j; 0 <= j < i && \at(a[j],Pre) < 0 ==> a[j] == 0;
    loop invariant \forall integer j; i <= j < n ==> a[j] == \at(a[j],Pre);
    loop assigns i, a[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (a[i] < 0) {
      a[i] = 0;
    }
  }
}
