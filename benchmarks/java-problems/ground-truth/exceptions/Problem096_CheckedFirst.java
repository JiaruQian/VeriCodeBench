public class Problem096_CheckedFirst {


    /*@
  @ public normal_behavior
  @ requires a != null && a.length > 0;
  @ assignable \nothing;
  @ ensures \result == a[0];
  @ also
  @ public exceptional_behavior
  @ requires a == null || (a != null && a.length == 0);
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int checkedFirst(int[] a) {
    if (a == null || a.length == 0) throw new IllegalArgumentException();
    return a[0];
    }

}
