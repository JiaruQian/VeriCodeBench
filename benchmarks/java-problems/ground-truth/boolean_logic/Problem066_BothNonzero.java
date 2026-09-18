public class Problem066_BothNonzero {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (x != 0 && y != 0);
  @*/
    public static boolean bothNonzero(int x, int y) {
    return x != 0 && y != 0;
    }

}
