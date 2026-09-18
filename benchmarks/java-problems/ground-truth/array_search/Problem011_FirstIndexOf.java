public class Problem011_FirstIndexOf {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures -1 <= \result && \result < a.length;
  @ ensures \result == -1 ==> (\forall int k; 0 <= k && k < a.length; a[k] != target);
  @ ensures \result >= 0 ==> a[\result] == target;
  @ ensures \result >= 0 ==> (\forall int k; 0 <= k && k < \result; a[k] != target);
  @*/
    public static int indexOf(int[] a, int target) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] != target);
    //@ loop_assigns i;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] == target) return i;
        i++;
    }
    return -1;
    }

}
