struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

int point_manhattan_nonneg(struct Point const *p) {
  return p->x + p->y;
}
