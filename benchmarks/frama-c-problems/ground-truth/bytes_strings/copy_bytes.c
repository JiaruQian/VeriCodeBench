/*@
  requires n >= 0;
  requires \valid(dst + (0..n-1)) && \valid_read(src + (0..n-1));
  requires \separated(dst + (0..n-1), src + (0..n-1));
  assigns dst[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> dst[j] == src[j];
*/
void copy_bytes(unsigned char *dst, unsigned char const *src, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> dst[j] == src[j];
    loop assigns i, dst[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    dst[i] = src[i];
  }
}
