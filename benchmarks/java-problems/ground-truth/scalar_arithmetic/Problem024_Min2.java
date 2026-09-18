public class Problem024_Min2 {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <= x && \result <= y;
  @ ensures \result == x || \result == y;
  @*/
    public static int min2(int x, int y) {
    return x <= y ? x : y;
    }

}
