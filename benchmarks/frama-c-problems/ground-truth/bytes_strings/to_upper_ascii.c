/*@
  assigns \nothing;
  ensures (c >= 'a' && c <= 'z') ==> \result == c - 32;
  ensures !(c >= 'a' && c <= 'z') ==> \result == c;
*/
char to_upper_ascii(char c) {
  if (c >= 'a' && c <= 'z') {
    return (char)(c - 32);
  }
  return c;
}
