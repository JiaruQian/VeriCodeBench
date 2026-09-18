public class Problem052_SafeNegate {


    /*@
  @ public normal_behavior
  @ requires x != Integer.MIN_VALUE;
  @ assignable \nothing;
  @ ensures \result == -x;
  @*/
    public static int safeNegate(int x) {
    return -x;
    }

}
