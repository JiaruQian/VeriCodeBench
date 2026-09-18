void elementwise_max(int *out, int const *a, int const *b, int n) {
  for (int i = 0; i < n; i++) {
    if (a[i] >= b[i]) {
      out[i] = a[i];
    } else {
      out[i] = b[i];
    }
  }
}
