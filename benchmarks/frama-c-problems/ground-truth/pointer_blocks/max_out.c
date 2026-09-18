/*@
  requires \valid_read(a) && \valid_read(b) && \valid(out);
  requires \separated(out, a) && \separated(out, b);
  assigns *out;
  ensures *out >= *a && *out >= *b;
  ensures *out == *a || *out == *b;
*/
void max_out(int const *a, int const *b, int *out) {
  if (*a >= *b) {
    *out = *a;
  } else {
    *out = *b;
  }
}
