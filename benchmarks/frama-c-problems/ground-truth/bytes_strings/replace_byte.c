/*@
  requires n >= 0;
  requires \valid(buf + (0..n-1));
  assigns buf[0..n-1];
  ensures \forall integer j; 0 <= j < n && \old(buf[j]) == old_value ==> buf[j] == new_value;
  ensures \forall integer j; 0 <= j < n && \old(buf[j]) != old_value ==> buf[j] == \old(buf[j]);
*/
void replace_byte(unsigned char *buf, int n, unsigned char old_value, unsigned char new_value) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i && \at(buf[j],Pre) == old_value ==> buf[j] == new_value;
    loop invariant \forall integer j; 0 <= j < i && \at(buf[j],Pre) != old_value ==> buf[j] == \at(buf[j],Pre);
    loop invariant \forall integer j; i <= j < n ==> buf[j] == \at(buf[j],Pre);
    loop assigns i, buf[0..n-1];
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (buf[i] == old_value) {
      buf[i] = new_value;
    }
  }
}
