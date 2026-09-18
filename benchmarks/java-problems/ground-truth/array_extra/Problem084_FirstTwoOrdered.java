public class Problem084_FirstTwoOrdered {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable \nothing;
  @ ensures \result <==> a[0] <= a[1];
  @*/
    public static boolean firstTwoOrdered(int[] a) {
    return a[0] <= a[1];
    }

}
