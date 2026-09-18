public class Problem074_SetLast {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable a[a.length - 1];
  @ ensures a[a.length - 1] == v;
  @*/
    public static void setLast(int[] a, int v) {
    a[a.length - 1] = v;
    }

}
