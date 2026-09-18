public class Problem027_SafeAdd {


    /*@
  @ public normal_behavior
  @ requires Integer.MIN_VALUE <= (long)x + (long)y && (long)x + (long)y <= Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == x + y;
  @*/
    public static int safeAdd(int x, int y) {
    return x + y;
    }

}
