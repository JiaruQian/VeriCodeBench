public class Problem007_SwapTwoIndices {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires 0 <= i && i < a.length;
  @ requires 0 <= j && j < a.length;
  @ assignable a[i], a[j];
  @ ensures a[i] == \old(a[j]);
  @ ensures a[j] == \old(a[i]);
  @*/
    public static void swap(int[] a, int i, int j) {
    int t = a[i];
    a[i] = a[j];
    a[j] = t;
    }

}
