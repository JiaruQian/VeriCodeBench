int is_all_zero(int const *a, int n) {
  for (int i = 0; i < n; i++) {
    if (a[i] != 0) {
      return 0;
    }
  }
  return 1;
}
