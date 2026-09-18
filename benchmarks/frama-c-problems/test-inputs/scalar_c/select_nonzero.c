int select_nonzero(int x, int fallback) {
  if (x != 0) {
    return x;
  }
  return fallback;
}
