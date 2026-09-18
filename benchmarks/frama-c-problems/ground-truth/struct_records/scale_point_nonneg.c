struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(p);
  requires p->x >= 0 && p->y >= 0 && factor >= 0;
  requires p->x * factor <= 2147483647 && p->y * factor <= 2147483647;
  assigns p->x, p->y;
  ensures p->x == \old(p->x) * factor;
  ensures p->y == \old(p->y) * factor;
*/
void scale_point_nonneg(struct Point *p, int factor) {
  p->x = p->x * factor;
  p->y = p->y * factor;
}
