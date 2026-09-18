public class Problem021_AdjacentSwapIfDescending {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires 0 <= i && i + 1 < a.length;
  @ assignable a[i], a[i+1];
  @ ensures a[i] <= a[i+1];
  @ ensures a[i] == \old(a[i]) || a[i] == \old(a[i+1]);
  @ ensures a[i+1] == \old(a[i]) || a[i+1] == \old(a[i+1]);
  @*/
    public static void swapIfDescending(int[] a, int i) {
    if (a[i] > a[i + 1]) {
        int t = a[i];
        a[i] = a[i + 1];
        a[i + 1] = t;
    }
    }

}
