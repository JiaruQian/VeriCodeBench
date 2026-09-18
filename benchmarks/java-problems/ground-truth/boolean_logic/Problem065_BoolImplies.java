public class Problem065_BoolImplies {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> (!a || b);
  @*/
    public static boolean implies(boolean a, boolean b) {
    return !a || b;
    }

}
