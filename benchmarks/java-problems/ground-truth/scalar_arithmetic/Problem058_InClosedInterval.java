public class Problem058_InClosedInterval {


    /*@
  @ public normal_behavior
  @ requires lo <= hi;
  @ assignable \nothing;
  @ ensures \result <==> (lo <= x && x <= hi);
  @*/
    public static boolean inClosedInterval(int x, int lo, int hi) {
    return lo <= x && x <= hi;
    }

}
