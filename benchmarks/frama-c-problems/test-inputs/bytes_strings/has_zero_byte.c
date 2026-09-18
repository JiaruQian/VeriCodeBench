int has_zero_byte(unsigned char const *buf, int n) {
  for (int i = 0; i < n; i++) {
    if (buf[i] == 0) {
      return 1;
    }
  }
  return 0;
}
