public class Problem072_ArrayHasLengthAtLeast {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires n >= 0;
  @ assignable \nothing;
  @ ensures \result <==> a.length >= n;
  @*/
    public static boolean hasLengthAtLeast(int[] a, int n) {
    return a.length >= n;
    }

}
