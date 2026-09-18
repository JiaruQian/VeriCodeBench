public class Problem053_SquareSmall {


    /*@
  @ public normal_behavior
  @ requires -46340 <= x && x <= 46340;
  @ assignable \nothing;
  @ ensures \result == x * x;
  @ ensures \result >= 0;
  @*/
    public static int square(int x) {
    return x * x;
    }

}
