public class Problem059_StrictBetween {


    /*@
  @ public normal_behavior
  @ requires lo < hi;
  @ assignable \nothing;
  @ ensures \result <==> (lo < x && x < hi);
  @*/
    public static boolean strictlyBetween(int x, int lo, int hi) {
    return lo < x && x < hi;
    }

}
