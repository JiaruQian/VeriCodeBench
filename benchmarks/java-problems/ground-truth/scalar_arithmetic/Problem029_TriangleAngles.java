public class Problem029_TriangleAngles {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b + (long)c == 180L);
  @*/
    public static boolean validTriangleAngles(int a, int b, int c) {
    return a > 0 && b > 0 && c > 0 && (long)a + (long)b + (long)c == 180L;
    }

}
