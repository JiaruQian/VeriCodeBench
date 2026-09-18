/*@
  requires x >= 0 && y > 0;
  requires \valid(q) && \valid(r);
  requires \separated(q, r);
  assigns *q, *r;
  ensures x == y * (*q) + *r;
  ensures 0 <= *r < y;
*/
void div_rem_nonneg(int x, int y, int *q, int *r) {
  *q = x / y;
  *r = x % y;
}
