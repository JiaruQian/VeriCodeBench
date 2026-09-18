public class Problem026_Clamp {


    /*@
  @ public normal_behavior
  @ requires lo <= hi;
  @ assignable \nothing;
  @ ensures lo <= \result && \result <= hi;
  @ ensures (lo <= x && x <= hi) ==> \result == x;
  @ ensures x < lo ==> \result == lo;
  @ ensures x > hi ==> \result == hi;
  @*/
    public static int clamp(int x, int lo, int hi) {
    if (x < lo) return lo;
    if (x > hi) return hi;
    return x;
    }

}
