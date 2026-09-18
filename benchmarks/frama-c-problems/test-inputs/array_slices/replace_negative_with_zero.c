void replace_negative_with_zero(int *a, int n) {
  for (int i = 0; i < n; i++) {
    if (a[i] < 0) {
      a[i] = 0;
    }
  }
}
