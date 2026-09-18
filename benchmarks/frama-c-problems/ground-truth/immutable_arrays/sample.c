/*@
    requires x >= 0;
    requires y > 0;
    assigns \nothing;
    ensures \result >= 0;
    ensures \result * y <= x;
    ensures x < (\result + 1) * y;
*/
int fun(int x, int y) {
    int r = x;
    int d = 0;
    /*@
        loop invariant r >= 0;
        loop invariant d >= 0;
        loop invariant r + d*y == x;
        loop assigns r, d;
        loop variant r;
    */
    while (r >= y) {
        r = r - y;
        d = d + 1;
    }
    return d;
}
