public class Problem080_LastIsPositive {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable \nothing;
  @ ensures \result <==> a[a.length - 1] > 0;
  @*/
    public static boolean lastIsPositive(int[] a) {
    return a[a.length - 1] > 0;
    }

}
