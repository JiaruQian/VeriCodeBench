struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

void reset_negative_counter(struct Counter *c) {
  if (c->value < 0) {
    c->value = 0;
  }
}
