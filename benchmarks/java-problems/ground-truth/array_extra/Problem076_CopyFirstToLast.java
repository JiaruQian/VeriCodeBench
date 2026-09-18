public class Problem076_CopyFirstToLast {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable a[a.length - 1];
  @ ensures a[a.length - 1] == \old(a[0]);
  @*/
    public static void copyFirstToLast(int[] a) {
    a[a.length - 1] = a[0];
    }

}
