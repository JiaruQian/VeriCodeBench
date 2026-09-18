public class Problem094_RequireNonnegative {


    /*@
  @ public normal_behavior
  @ requires x >= 0;
  @ assignable \nothing;
  @ ensures \result == x;
  @ also
  @ public exceptional_behavior
  @ requires x < 0;
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int requireNonnegative(int x) {
    if (x < 0) throw new IllegalArgumentException();
    return x;
    }

}
