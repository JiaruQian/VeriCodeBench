/*@
  requires \valid(dst) && \valid_read(src);
  requires \separated(dst, src);
  assigns *dst;
  ensures *src > 0 ==> *dst == *src;
  ensures *src <= 0 ==> *dst == \old(*dst);
*/
void copy_if_positive(int *dst, int const *src) {
  if (*src > 0) {
    *dst = *src;
  }
}
