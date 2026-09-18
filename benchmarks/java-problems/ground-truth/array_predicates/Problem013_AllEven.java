public class Problem013_AllEven {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures \result <==> (\forall int k; 0 <= k && k < a.length; a[k] % 2 == 0);
  @*/
    public static boolean allEven(int[] a) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] % 2 == 0);
    //@ loop_assigns i;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] % 2 != 0) return false;
        i++;
    }
    return true;
    }

}
