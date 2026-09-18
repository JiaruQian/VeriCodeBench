/*@
  requires \valid_read(a) && \valid_read(b) && \valid(lo) && \valid(hi);
  requires \separated(lo, hi, a, b);
  assigns *lo, *hi;
  ensures *lo <= *hi;
  ensures *lo == *a || *lo == *b;
  ensures *hi == *a || *hi == *b;
*/
void minmax_out(int const *a, int const *b, int *lo, int *hi) {
  if (*a <= *b) {
    *lo = *a;
    *hi = *b;
  } else {
    *lo = *b;
    *hi = *a;
  }
}
