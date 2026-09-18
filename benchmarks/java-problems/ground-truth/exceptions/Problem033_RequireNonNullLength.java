public class Problem033_RequireNonNullLength {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures \result == a.length;
  @ also
  @ public exceptional_behavior
  @ requires a == null;
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int requireLength(int[] a) {
    if (a == null) throw new IllegalArgumentException();
    return a.length;
    }

}
