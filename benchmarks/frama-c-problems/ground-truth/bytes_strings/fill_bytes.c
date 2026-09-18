/*@
  requires n >= 0;
  requires \valid(buf + (0..n-1));
  assigns buf[0..n-1];
  ensures \forall integer j; 0 <= j < n ==> buf[j] == value;
*/
void fill_bytes(unsigned char *buf, int n, unsigned char value) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> buf[j] == value;
    loop assigns i, buf[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    buf[i] = value;
  }
}
