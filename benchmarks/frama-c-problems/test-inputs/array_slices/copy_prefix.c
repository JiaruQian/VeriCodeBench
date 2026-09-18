void copy_prefix(int *dst, int const *src, int n, int k) {
  for (int i = 0; i < k; i++) {
    dst[i] = src[i];
  }
}
