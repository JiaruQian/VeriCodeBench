/*@
  assigns \nothing;
  ensures \result == 0 || \result == 1;
  ensures x % 2 == 0 ==> \result == 1;
  ensures x % 2 != 0 ==> \result == 0;
*/
int is_even_mod(int x) {
  if (x % 2 == 0) {
    return 1;
  }
  return 0;
}
