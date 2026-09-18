public class Problem018_IncrementAll {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires (\forall int k; 0 <= k && k < a.length; a[k] < Integer.MAX_VALUE);
  @ assignable a[*];
  @ ensures (\forall int k; 0 <= k && k < a.length; a[k] == \old(a[k]) + 1);
  @*/
    public static void incrementAll(int[] a) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] == \old(a[k]) + 1);
    //@ loop_invariant (\forall int k; i <= k && k < a.length; a[k] == \old(a[k]));
    //@ loop_assigns i, a[*];
    //@ decreases a.length - i;
    while (i < a.length) {
        //@ assert a[i] < Integer.MAX_VALUE;
        a[i] = a[i] + 1;
        i++;
    }
    }

}
