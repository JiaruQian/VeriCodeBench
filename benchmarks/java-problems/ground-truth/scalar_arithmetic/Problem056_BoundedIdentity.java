public class Problem056_BoundedIdentity {


    /*@
  @ public normal_behavior
  @ requires lo <= x && x <= hi;
  @ assignable \nothing;
  @ ensures \result == x;
  @ ensures lo <= \result && \result <= hi;
  @*/
    public static int boundedIdentity(int x, int lo, int hi) {
    return x;
    }

}
