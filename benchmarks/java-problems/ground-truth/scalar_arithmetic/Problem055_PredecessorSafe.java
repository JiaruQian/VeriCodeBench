public class Problem055_PredecessorSafe {


    /*@
  @ public normal_behavior
  @ requires x > Integer.MIN_VALUE;
  @ assignable \nothing;
  @ ensures \result == x - 1;
  @*/
    public static int predecessor(int x) {
    return x - 1;
    }

}
