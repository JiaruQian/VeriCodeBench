public class Problem012_CountValue {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures 0 <= \result && \result <= a.length;
  @*/
    public static int countValue(int[] a, int target) {
    int c = 0;
    int i = 0;
    //@ loop_invariant 0 <= i && i <= a.length;
    //@ loop_invariant 0 <= c && c <= i;
    //@ loop_assigns i, c;
    //@ decreases a.length - i;
    while (i < a.length) {
        if (a[i] == target) c++;
        i++;
    }
    return c;
    }

}
