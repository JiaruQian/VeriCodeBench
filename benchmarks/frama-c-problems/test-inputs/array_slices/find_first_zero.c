int find_first_zero(int const *a, int n) {
  for (int i = 0; i < n; i++) {
    if (a[i] == 0) {
      return i;
    }
  }
  return -1;
}
