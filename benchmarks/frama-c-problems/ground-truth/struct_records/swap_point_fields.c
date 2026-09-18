struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(p);
  assigns p->x, p->y;
  ensures p->x == \old(p->y);
  ensures p->y == \old(p->x);
*/
void swap_point_fields(struct Point *p) {
  int t = p->x;
  p->x = p->y;
  p->y = t;
}
