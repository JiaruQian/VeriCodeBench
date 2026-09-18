public class Problem075_IncrementFirstSafe {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ requires a[0] < Integer.MAX_VALUE;
  @ assignable a[0];
  @ ensures a[0] == \old(a[0]) + 1;
  @*/
    public static void incrementFirst(int[] a) {
    a[0] = a[0] + 1;
    }

}
