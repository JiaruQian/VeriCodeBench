public class Problem068_AllThreePositive {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (a > 0 && b > 0 && c > 0);
  @*/
    public static boolean allThreePositive(int a, int b, int c) {
    return a > 0 && b > 0 && c > 0;
    }

}
