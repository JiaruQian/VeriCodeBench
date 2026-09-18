struct Point { int x; int y; };
struct Range { int lo; int hi; };
struct Counter { int value; int limit; };
struct Rect { int width; int height; };

/*@
  requires \valid(c);
  requires c->value < c->limit ==> c->value < 2147483647;
  assigns c->value;
  ensures \old(c->value) < \old(c->limit) ==> c->value == \old(c->value) + 1;
  ensures \old(c->value) >= \old(c->limit) ==> c->value == \old(c->value);
  ensures c->limit == \old(c->limit);
*/
void counter_inc_if_below_limit(struct Counter *c) {
  if (c->value < c->limit) {
    c->value = c->value + 1;
  }
}
