public class Problem097_CheckedLast {


    /*@
  @ public normal_behavior
  @ requires a != null && a.length > 0;
  @ assignable \nothing;
  @ ensures \result == a[a.length - 1];
  @ also
  @ public exceptional_behavior
  @ requires a == null || (a != null && a.length == 0);
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int checkedLast(int[] a) {
    if (a == null || a.length == 0) throw new IllegalArgumentException();
    return a[a.length - 1];
    }

}
