public class Problem100_CheckedSuccessor {


    /*@
  @ public normal_behavior
  @ requires x < Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == x + 1;
  @ also
  @ public exceptional_behavior
  @ requires x == Integer.MAX_VALUE;
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int checkedSuccessor(int x) {
    if (x == Integer.MAX_VALUE) throw new IllegalArgumentException();
    return x + 1;
    }

}
