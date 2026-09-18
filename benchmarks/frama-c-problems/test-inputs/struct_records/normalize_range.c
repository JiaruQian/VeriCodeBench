struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void normalize_range(struct Range *r) {
  if (r->lo > r->hi) {
    int t = r->lo;
    r->lo = r->hi;
    r->hi = t;
  }
}
