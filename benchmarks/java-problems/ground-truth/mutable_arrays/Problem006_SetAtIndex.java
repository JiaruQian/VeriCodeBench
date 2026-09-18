public class Problem006_SetAtIndex {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires 0 <= i && i < a.length;
  @ assignable a[i];
  @ ensures a[i] == v;
  @ ensures (\forall int k; 0 <= k && k < a.length && k != i; a[k] == \old(a[k]));
  @*/
    public static void setAt(int[] a, int i, int v) {
    a[i] = v;
    }

}
