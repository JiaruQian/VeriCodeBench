public class Problem079_FirstIsZero {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable \nothing;
  @ ensures \result <==> a[0] == 0;
  @*/
    public static boolean firstIsZero(int[] a) {
    return a[0] == 0;
    }

}
