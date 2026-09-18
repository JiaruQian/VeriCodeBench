public class Problem078_ThreeArraySumSafe {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length == 3;
  @ requires Integer.MIN_VALUE <= (long)a[0] + (long)a[1] && (long)a[0] + (long)a[1] <= Integer.MAX_VALUE;
  @ requires Integer.MIN_VALUE <= (long)(a[0] + a[1]) + (long)a[2] && (long)(a[0] + a[1]) + (long)a[2] <= Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == a[0] + a[1] + a[2];
  @*/
    public static int sum3Array(int[] a) {
    return a[0] + a[1] + a[2];
    }

}
