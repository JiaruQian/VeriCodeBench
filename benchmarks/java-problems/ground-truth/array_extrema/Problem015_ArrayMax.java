public class Problem015_ArrayMax {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable \nothing;
  @ ensures (\forall int k; 0 <= k && k < a.length; \result >= a[k]);
  @ ensures (\exists int k; 0 <= k && k < a.length; \result == a[k]);
  @*/
    public static int max(int[] a) {
    int m = a[0];
    int i = 1;
    //@ loop_invariant 1 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; m >= a[k]);
    //@ loop_invariant (\exists int k; 0 <= k && k < i; m == a[k]);
    //@ loop_assigns i, m;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] > m) m = a[i];
        i++;
    }
    return m;
    }

}
