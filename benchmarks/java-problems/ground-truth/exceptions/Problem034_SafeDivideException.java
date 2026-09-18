public class Problem034_SafeDivideException {


    /*@
  @ public normal_behavior
  @ requires y != 0;
  @ requires !(x == Integer.MIN_VALUE && y == -1);
  @ assignable \nothing;
  @ ensures \result == x / y;
  @ also
  @ public exceptional_behavior
  @ requires y == 0;
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int divide(int x, int y) {
    if (y == 0) throw new IllegalArgumentException();
    return x / y;
    }

}
