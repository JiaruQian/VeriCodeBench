/*@
  assigns \nothing;
  ensures \result == 0 || \result == 1;
  ensures (c >= '0' && c <= '9') ==> \result == 1;
  ensures !(c >= '0' && c <= '9') ==> \result == 0;
*/
int is_ascii_digit(char c) {
  if (c >= '0' && c <= '9') {
    return 1;
  }
  return 0;
}
