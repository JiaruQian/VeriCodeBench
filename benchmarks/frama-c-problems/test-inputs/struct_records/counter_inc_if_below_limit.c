struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void counter_inc_if_below_limit(struct Counter *c) {
  if (c->value < c->limit) {
    c->value = c->value + 1;
  }
}
