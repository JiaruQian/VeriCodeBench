void fill_bytes(unsigned char *buf, int n, unsigned char value) {
  for (int i = 0; i < n; i++) {
    buf[i] = value;
  }
}
