void swap_first_last(int *a, int n) {
  int t = a[0];
  a[0] = a[n - 1];
  a[n - 1] = t;
}
