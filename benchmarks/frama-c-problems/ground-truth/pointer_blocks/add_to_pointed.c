/*@
  requires \valid(x);
  requires -2147483648 <= *x + delta <= 2147483647;
  assigns *x;
  ensures *x == \old(*x) + delta;
*/
void add_to_pointed(int *x, int delta) {
  *x = *x + delta;
}
