public class Problem025_AbsNonMin {


    /*@
  @ public normal_behavior
  @ requires x != Integer.MIN_VALUE;
  @ assignable \nothing;
  @ ensures \result >= 0;
  @ ensures \result == x || \result == -x;
  @*/
    public static int abs(int x) {
    return x >= 0 ? x : -x;
    }

}
