void reverse_three(int *a, int n) {
  int t = a[0];
  a[0] = a[2];
  a[2] = t;
}
