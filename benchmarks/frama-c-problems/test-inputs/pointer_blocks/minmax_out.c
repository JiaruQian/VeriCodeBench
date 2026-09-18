void minmax_out(int const *a, int const *b, int *lo, int *hi) {
  if (*a <= *b) {
    *lo = *a;
    *hi = *b;
  } else {
    *lo = *b;
    *hi = *a;
  }
}
