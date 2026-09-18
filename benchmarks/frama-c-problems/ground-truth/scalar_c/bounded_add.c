/*@
  requires -2147483648 <= x + y <= 2147483647;
  assigns \nothing;
  ensures \result == x + y;
*/
int bounded_add(int x, int y) {
  return x + y;
}
