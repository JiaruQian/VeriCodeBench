struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid_read(p);
  requires p->x >= 0 && p->y >= 0;
  requires p->x + p->y <= 2147483647;
  assigns \nothing;
  ensures \result == p->x + p->y;
*/
int point_manhattan_nonneg(struct Point const *p) {
  return p->x + p->y;
}
