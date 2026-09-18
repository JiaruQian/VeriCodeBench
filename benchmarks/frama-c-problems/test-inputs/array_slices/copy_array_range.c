void copy_array_range(int *dst, int const *src, int n) {
  for (int i = 0; i < n; i++) {
    dst[i] = src[i];
  }
}
