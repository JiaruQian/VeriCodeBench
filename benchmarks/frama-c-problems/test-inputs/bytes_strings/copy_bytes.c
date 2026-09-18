void copy_bytes(unsigned char *dst, unsigned char const *src, int n) {
  for (int i = 0; i < n; i++) {
    dst[i] = src[i];
  }
}
