void replace_byte(unsigned char *buf, int n, unsigned char old_value, unsigned char new_value) {
  for (int i = 0; i < n; i++) {
    if (buf[i] == old_value) {
      buf[i] = new_value;
    }
  }
}
