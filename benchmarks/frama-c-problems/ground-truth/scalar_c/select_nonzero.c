/*@
  assigns \nothing;
  ensures x != 0 ==> \result == x;
  ensures x == 0 ==> \result == fallback;
*/
int select_nonzero(int x, int fallback) {
  if (x != 0) {
    return x;
  }
  return fallback;
}
