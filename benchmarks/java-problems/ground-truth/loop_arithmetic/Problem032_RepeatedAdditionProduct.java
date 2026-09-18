public class Problem032_RepeatedAdditionProduct {


    /*@
  @ public normal_behavior
  @ requires 0 <= a && a <= 10000;
  @ requires -10000 <= b && b <= 10000;
  @ assignable \nothing;
  @ ensures \result == a * b;
  @*/
    public static int multiplyByRepeatedAdd(int a, int b) {
    int r = 0;
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a;
    //@ loop_invariant r == i * b;
    //@ loop_assigns i, r;
    //@ decreases a - i;
    while (i < a) {
        r += b;
        i++;
    }
    return r;
    }

}
