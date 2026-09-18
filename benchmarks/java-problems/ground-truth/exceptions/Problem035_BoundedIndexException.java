public class Problem035_BoundedIndexException {


    /*@
  @ public normal_behavior
  @ requires a != null && 0 <= i && i < a.length;
  @ assignable \nothing;
  @ ensures \result == a[i];
  @ also
  @ public exceptional_behavior
  @ requires a == null || i < 0 || (a != null && i >= a.length);
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int checkedGet(int[] a, int i) {
    if (a == null || i < 0 || i >= a.length) throw new IllegalArgumentException();
    return a[i];
    }

}
