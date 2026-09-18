struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(p);
  assigns p->x, p->y;
  ensures p->x == x && p->y == y;
*/
void set_point(struct Point *p, int x, int y) {
  p->x = x;
  p->y = y;
}
