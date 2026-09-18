public class Problem030_TriangleSides {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b > (long)c && (long)a + (long)c > (long)b && (long)b + (long)c > (long)a);
  @*/
    public static boolean validTriangleSides(int a, int b, int c) {
    return a > 0 && b > 0 && c > 0 && (long)a + (long)b > (long)c && (long)a + (long)c > (long)b && (long)b + (long)c > (long)a;
    }

}
