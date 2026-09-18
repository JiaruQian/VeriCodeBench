struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid_read(r);
  requires r->width >= 0 && r->height >= 0;
  requires r->width * r->height <= 2147483647;
  assigns \nothing;
  ensures \result == r->width * r->height;
*/
int rect_area(struct Rect const *r) {
  return r->width * r->height;
}
