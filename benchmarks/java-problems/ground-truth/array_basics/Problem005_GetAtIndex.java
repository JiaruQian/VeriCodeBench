public class Problem005_GetAtIndex {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires 0 <= i && i < a.length;
  @ assignable \nothing;
  @ ensures \result == a[i];
  @*/
    public static int getAt(int[] a, int i) {
    return a[i];
    }

}
