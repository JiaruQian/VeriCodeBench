public class Problem010_ContainsValue {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures \result <==> (\exists int k; 0 <= k && k < a.length; a[k] == target);
  @*/
    public static boolean contains(int[] a, int target) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] != target);
    //@ loop_assigns i;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] == target) return true;
        i++;
    }
    return false;
    }

}
