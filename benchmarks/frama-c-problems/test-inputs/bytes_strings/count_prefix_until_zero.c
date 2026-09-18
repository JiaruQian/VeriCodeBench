int count_prefix_until_zero(unsigned char const *buf, int n) {
  for (int i = 0; i < n; i++) {
    if (buf[i] == 0) {
      return i;
    }
  }
  return n;
}
