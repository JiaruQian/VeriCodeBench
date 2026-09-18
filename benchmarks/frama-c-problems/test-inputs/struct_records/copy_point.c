struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void copy_point(struct Point *dst, struct Point const *src) {
  dst->x = src->x;
  dst->y = src->y;
}
