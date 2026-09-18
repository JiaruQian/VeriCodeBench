struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

int rect_area(struct Rect const *r) {
  return r->width * r->height;
}
