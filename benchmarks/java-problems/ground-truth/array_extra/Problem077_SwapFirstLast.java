public class Problem077_SwapFirstLast {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable a[0], a[a.length - 1];
  @ ensures a[0] == \old(a[a.length - 1]);
  @ ensures a[a.length - 1] == \old(a[0]);
  @*/
    public static void swapFirstLast(int[] a) {
    int t = a[0];
    a[0] = a[a.length - 1];
    a[a.length - 1] = t;
    }

}
