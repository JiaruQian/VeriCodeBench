public class Problem099_RequireSortedPair {


    /*@
  @ public normal_behavior
  @ requires x <= y;
  @ assignable \nothing;
  @ ensures \result == x;
  @ also
  @ public exceptional_behavior
  @ requires x > y;
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int requireSortedPair(int x, int y) {
    if (x > y) throw new IllegalArgumentException();
    return x;
    }

}
