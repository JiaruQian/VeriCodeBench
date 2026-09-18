public class Problem067_AtLeastOneZero {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (x == 0 || y == 0);
  @*/
    public static boolean atLeastOneZero(int x, int y) {
    return x == 0 || y == 0;
    }

}
