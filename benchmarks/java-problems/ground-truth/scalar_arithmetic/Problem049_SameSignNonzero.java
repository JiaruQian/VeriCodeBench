public class Problem049_SameSignNonzero {


    /*@
  @ public normal_behavior
  @ requires x != 0 && y != 0;
  @ assignable \nothing;
  @ ensures \result <==> ((x > 0 && y > 0) || (x < 0 && y < 0));
  @*/
    public static boolean sameSign(int x, int y) {
    return (x > 0 && y > 0) || (x < 0 && y < 0);
    }

}
