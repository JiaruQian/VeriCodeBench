struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void scale_point_nonneg(struct Point *p, int factor) {
  p->x = p->x * factor;
  p->y = p->y * factor;
}
