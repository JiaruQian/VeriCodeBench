/*@
  requires n > 0 && 0 <= idx < n;
  requires \valid(s + (0..n-1));
  assigns s[idx];
  ensures s[idx] == '\0';
  ensures \forall integer j; 0 <= j < n && j != idx ==> s[j] == \old(s[j]);
*/
void zero_terminate_at(char *s, int n, int idx) {
  s[idx] = '\0';
}
