struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(p);
  requires -2147483648 <= p->x + dx <= 2147483647;
  requires -2147483648 <= p->y + dy <= 2147483647;
  assigns p->x, p->y;
  ensures p->x == \old(p->x) + dx;
  ensures p->y == \old(p->y) + dy;
*/
void translate_point(struct Point *p, int dx, int dy) {
  p->x = p->x + dx;
  p->y = p->y + dy;
}
