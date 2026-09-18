public class Problem020_ReplaceEvenIndices {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable a[*];
  @ ensures (\forall int k; 0 <= k && k < a.length && k % 2 == 0; a[k] == 0);
  @ ensures (\forall int k; 0 <= k && k < a.length && k % 2 != 0; a[k] == \old(a[k]));
  @*/
    public static void clearEvenIndices(int[] a) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i && k % 2 == 0; a[k] == 0);
    //@ loop_invariant (\forall int k; 0 <= k && k < i && k % 2 != 0; a[k] == \old(a[k]));
    //@ loop_invariant (\forall int k; i <= k && k < a.length; a[k] == \old(a[k]));
    //@ loop_assigns i, a[*];
    //@ decreases a.length - i;
    while (i < a.length) {
        if (i % 2 == 0) a[i] = 0;
        i++;
    }
    }

}
