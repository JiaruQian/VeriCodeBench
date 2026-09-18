public class Problem014_AnyNegative {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures \result <==> (\exists int k; 0 <= k && k < a.length; a[k] < 0);
  @*/
    public static boolean anyNegative(int[] a) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] >= 0);
    //@ loop_assigns i;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] < 0) return true;
        i++;
    }
    return false;
    }

}
