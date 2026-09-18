struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(dst) && \valid_read(src);
  requires \separated(dst, src);
  assigns dst->x, dst->y;
  ensures dst->x == src->x && dst->y == src->y;
*/
void copy_point(struct Point *dst, struct Point const *src) {
  dst->x = src->x;
  dst->y = src->y;
}
