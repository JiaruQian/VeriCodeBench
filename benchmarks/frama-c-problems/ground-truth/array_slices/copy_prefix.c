/*@
  requires 0 <= k <= n;
  requires \valid(dst + (0..n-1)) && \valid_read(src + (0..k-1));
  requires \separated(dst + (0..n-1), src + (0..k-1));
  assigns dst[0..k-1];
  ensures \forall integer j; 0 <= j < k ==> dst[j] == src[j];
  ensures \forall integer j; k <= j < n ==> dst[j] == \old(dst[j]);
*/
void copy_prefix(int *dst, int const *src, int n, int k) {
  /*@
    loop invariant 0 <= i <= k;
    loop invariant \forall integer j; 0 <= j < i ==> dst[j] == src[j];
    loop invariant \forall integer j; i <= j < n ==> dst[j] == \at(dst[j],Pre);
    loop assigns i, dst[0..k-1];
    loop variant k - i;
  */
  for (int i = 0; i < k; i++) {
    dst[i] = src[i];
  }
}
