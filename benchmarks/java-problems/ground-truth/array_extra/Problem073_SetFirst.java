public class Problem073_SetFirst {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable a[0];
  @ ensures a[0] == v;
  @*/
    public static void setFirst(int[] a, int v) {
    a[0] = v;
    }

}
