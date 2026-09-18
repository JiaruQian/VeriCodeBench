public class Problem008_ZeroPrefix {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires 0 <= n && n <= a.length;
  @ assignable a[0 .. n-1];
  @ ensures (\forall int k; 0 <= k && k < n; a[k] == 0);
  @ ensures (\forall int k; n <= k && k < a.length; a[k] == \old(a[k]));
  @*/
    public static void zeroPrefix(int[] a, int n) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= n;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] == 0);
    //@ loop_assigns i, a[0 .. n-1];
    //@ decreases n - i;
    while (i < n) {
        a[i] = 0;
        i++;
    }
    }

}
