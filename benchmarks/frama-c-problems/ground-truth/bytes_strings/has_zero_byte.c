/*@
  requires n >= 0;
  requires \valid_read(buf + (0..n-1));
  assigns \nothing;
  ensures \result == 1 ==> \exists integer j; 0 <= j < n && buf[j] == 0;
  ensures \result == 0 ==> \forall integer j; 0 <= j < n ==> buf[j] != 0;
*/
int has_zero_byte(unsigned char const *buf, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> buf[j] != 0;
    loop assigns i;
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (buf[i] == 0) {
      return 1;
    }
  }
  return 0;
}
