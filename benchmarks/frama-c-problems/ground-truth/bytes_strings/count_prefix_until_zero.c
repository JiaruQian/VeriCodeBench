/*@
  requires n >= 0;
  requires \valid_read(buf + (0..n-1));
  requires \exists integer j; 0 <= j < n && buf[j] == 0;
  assigns \nothing;
  ensures 0 <= \result < n;
  ensures buf[\result] == 0;
  ensures \forall integer j; 0 <= j < \result ==> buf[j] != 0;
*/
int count_prefix_until_zero(unsigned char const *buf, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> buf[j] != 0;
    loop assigns i;
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (buf[i] == 0) {
      return i;
    }
  }
  return n;
}
