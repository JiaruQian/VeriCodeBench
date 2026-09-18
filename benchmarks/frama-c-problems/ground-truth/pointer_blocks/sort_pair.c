/*@
  requires \valid(a) && \valid(b);
  requires \separated(a, b);
  assigns *a, *b;
  ensures *a <= *b;
  ensures (*a == \old(*a) && *b == \old(*b)) || (*a == \old(*b) && *b == \old(*a));
*/
void sort_pair(int *a, int *b) {
  if (*a > *b) {
    int t = *a;
    *a = *b;
    *b = t;
  }
}
