void clamp_pointed(int *x, int lo, int hi) {
  if (*x < lo) {
    *x = lo;
  } else if (*x > hi) {
    *x = hi;
  }
}
