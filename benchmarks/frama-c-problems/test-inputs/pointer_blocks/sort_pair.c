void sort_pair(int *a, int *b) {
  if (*a > *b) {
    int t = *a;
    *a = *b;
    *b = t;
  }
}
