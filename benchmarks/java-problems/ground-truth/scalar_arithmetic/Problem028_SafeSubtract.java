public class Problem028_SafeSubtract {


    /*@
  @ public normal_behavior
  @ requires Integer.MIN_VALUE <= (long)x - (long)y && (long)x - (long)y <= Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == x - y;
  @*/
    public static int safeSubtract(int x, int y) {
    return x - y;
    }

}
