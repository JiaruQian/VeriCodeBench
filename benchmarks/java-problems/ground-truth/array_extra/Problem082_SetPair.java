public class Problem082_SetPair {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable a[0], a[1];
  @ ensures a[0] == x;
  @ ensures a[1] == y;
  @*/
    public static void setPair(int[] a, int x, int y) {
    a[0] = x;
    a[1] = y;
    }

}
