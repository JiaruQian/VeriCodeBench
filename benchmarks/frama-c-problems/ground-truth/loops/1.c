/*@
    assigns \nothing;
    ensures \result == 30;
*/
int loop_to_30(void) {
    int i = 0;
    /*@
        loop invariant 0 <= i <= 30;
        loop assigns i;
        loop variant 30 - i;
    */
    while (i < 30) {
        ++i;
    }
    return i;
}
