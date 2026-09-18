/*@
  requires n >= 0;
  requires \valid_read(s + (0..n-1));
  requires \exists integer j; 0 <= j < n && s[j] == '\0';
  assigns \nothing;
  ensures 0 <= \result < n;
  ensures s[\result] == '\0';
  ensures \forall integer j; 0 <= j < \result ==> s[j] != '\0';
*/
int bounded_strlen(char const *s, int n) {
  /*@
    loop invariant 0 <= i <= n;
    loop invariant \forall integer j; 0 <= j < i ==> s[j] != '\0';
    loop assigns i;
    loop variant n - i;
  */
  for (int i = 0; i < n; i++) {
    if (s[i] == '\0') {
      return i;
    }
  }
  return n;
}
