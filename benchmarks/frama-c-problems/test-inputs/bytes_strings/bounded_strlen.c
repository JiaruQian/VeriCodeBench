int bounded_strlen(char const *s, int n) {
  for (int i = 0; i < n; i++) {
    if (s[i] == '\0') {
      return i;
    }
  }
  return n;
}
