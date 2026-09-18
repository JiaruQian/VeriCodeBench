void zero_at_if_negative(int *a, int n, int idx) {
  if (a[idx] < 0) {
    a[idx] = 0;
  }
}
