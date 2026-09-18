public class Problem009_FillArray {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable a[*];
  @ ensures (\forall int k; 0 <= k && k < a.length; a[k] == v);
  @*/
    public static void fill(int[] a, int v) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; a[k] == v);
    //@ loop_assigns i, a[*];
    //@ decreases a.length - i;
    while (i < a.length) {
        a[i] = v;
        i++;
    }
    }

}
