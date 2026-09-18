/*@
  requires 0 <= k <= n;
  requires \valid(a + (0..n-1));
  assigns a[0..k-1];
  ensures \forall integer j; 0 <= j < k ==> a[j] == value;
  ensures \forall integer j; k <= j < n ==> a[j] == \old(a[j]);
*/
void fill_prefix_value(int *a, int n, int k, int value) {
  /*@
    loop invariant 0 <= i <= k;
    loop invariant \forall integer j; 0 <= j < i ==> a[j] == value;
    loop invariant \forall integer j; i <= j < n ==> a[j] == \at(a[j],Pre);
    loop assigns i, a[0..k-1];
    loop variant k - i;
  */
  for (int i = 0; i < k; i++) {
    a[i] = value;
  }
}
