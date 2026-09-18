/*@
  requires n > 0;
  requires \valid_read(a + (0..n-1));
  assigns \nothing;
  ensures \result == a[0];
*/
int get_first(int const *a, int n) {
  return a[0];
}
