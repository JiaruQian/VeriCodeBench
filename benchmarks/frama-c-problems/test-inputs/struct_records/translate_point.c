struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void translate_point(struct Point *p, int dx, int dy) {
  p->x = p->x + dx;
  p->y = p->y + dy;
}
