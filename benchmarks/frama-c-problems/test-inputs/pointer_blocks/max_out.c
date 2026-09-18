void max_out(int const *a, int const *b, int *out) {
  if (*a >= *b) {
    *out = *a;
  } else {
    *out = *b;
  }
}
