public class Problem019_DoubleAll {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires (\forall int k; 0 <= k && k < a.length; Integer.MIN_VALUE/2 <= a[k] && a[k] <= Integer.MAX_VALUE/2);
  @ assignable a[*];
  @ ensures (\forall int k; 0 <= k && k < a.length; a[k] == 2 * \old(a[k]));
  @*/
    public static void doubleAll(int[] a) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] == 2 * \old(a[k]));
    //@ loop_invariant (\forall int k; i <= k && k < a.length; a[k] == \old(a[k]));
    //@ loop_assigns i, a[*];
    //@ decreases a.length - i;
    while (i < a.length) {
        //@ assert Integer.MIN_VALUE/2 <= a[i] && a[i] <= Integer.MAX_VALUE/2;
        a[i] = 2 * a[i];
        i++;
    }
    }

}
