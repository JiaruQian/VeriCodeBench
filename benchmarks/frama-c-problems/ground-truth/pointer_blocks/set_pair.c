/*@
  requires \valid(a) && \valid(b);
  requires \separated(a, b);
  assigns *a, *b;
  ensures *a == x;
  ensures *b == y;
*/
void set_pair(int *a, int *b, int x, int y) {
  *a = x;
  *b = y;
}
