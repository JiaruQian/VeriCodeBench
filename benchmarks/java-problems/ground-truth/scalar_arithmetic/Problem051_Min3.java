public class Problem051_Min3 {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <= a && \result <= b && \result <= c;
  @ ensures \result == a || \result == b || \result == c;
  @*/
    public static int min3(int a, int b, int c) {
    int m = a <= b ? a : b;
    return m <= c ? m : c;
    }

}
