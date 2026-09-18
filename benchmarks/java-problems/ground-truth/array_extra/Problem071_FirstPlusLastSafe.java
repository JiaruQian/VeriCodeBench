public class Problem071_FirstPlusLastSafe {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ requires Integer.MIN_VALUE <= (long)a[0] + (long)a[a.length - 1] && (long)a[0] + (long)a[a.length - 1] <= Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == a[0] + a[a.length - 1];
  @*/
    public static int firstPlusLast(int[] a) {
    return a[0] + a[a.length - 1];
    }

}
