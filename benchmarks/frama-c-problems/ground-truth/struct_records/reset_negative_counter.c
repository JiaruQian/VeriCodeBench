struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(c);
  assigns c->value;
  ensures \old(c->value) < 0 ==> c->value == 0;
  ensures \old(c->value) >= 0 ==> c->value == \old(c->value);
  ensures c->limit == \old(c->limit);
*/
void reset_negative_counter(struct Counter *c) {
  if (c->value < 0) {
    c->value = 0;
  }
}
