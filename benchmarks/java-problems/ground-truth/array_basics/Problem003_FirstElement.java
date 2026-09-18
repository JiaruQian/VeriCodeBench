public class Problem003_FirstElement {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable \nothing;
  @ ensures \result == a[0];
  @*/
    public static int first(int[] a) {
    return a[0];
    }

}
