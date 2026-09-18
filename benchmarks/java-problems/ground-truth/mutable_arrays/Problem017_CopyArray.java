public class Problem017_CopyArray {


    /*@
  @ public normal_behavior
  @ requires src != null && dst != null;
  @ requires dst.length >= src.length;
  @ assignable dst[0 .. src.length-1];
  @ ensures (\forall int k; 0 <= k && k < src.length; dst[k] == src[k]);
  @*/
    public static void copy(int[] src, int[] dst) {
    int i = 0;
    //@ loop_invariant 0 <= i && i <= src.length;
    //@ loop_invariant (\forall int k; 0 <= k && k < i; dst[k] == src[k]);
    //@ loop_assigns i, dst[0 .. src.length-1];
    //@ decreases src.length - i;
    while (i < src.length) {
        dst[i] = src[i];
        i++;
    }
    }

}
