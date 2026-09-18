/*@
  requires n >= 0;
  requires \valid(out + (0..n-1)) && \valid_read(a + (0..n-1)) && \valid_read(b + (0..n-1));
  requires \separated(out + (0..n-1), a + (0..n-1), b + (0..n-1));
  assigns out[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> out[j] >= a[j] && out[j] >= b[j];
  ensures \forall integer j; 0 <= j < n ==> out[j] == a[j] || out[j] == b[j];
*/
void elementwise_max(int *out, int const *a, int const *b, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> out[j] >= a[j] && out[j] >= b[j];
    loop invariant \forall integer j; 0 <= j < i ==> out[j] == a[j] || out[j] == b[j];
    loop assigns i, out[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (a[i] >= b[i]) {
      out[i] = a[i];
    } else {
      out[i] = b[i];
    }
  }
}
