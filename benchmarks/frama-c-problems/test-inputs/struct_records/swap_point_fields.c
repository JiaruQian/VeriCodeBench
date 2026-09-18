struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void swap_point_fields(struct Point *p) {
  int t = p->x;
  p->x = p->y;
  p->y = t;
}
