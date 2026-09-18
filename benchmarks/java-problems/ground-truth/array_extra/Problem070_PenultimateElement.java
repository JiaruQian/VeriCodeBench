public class Problem070_PenultimateElement {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable \nothing;
  @ ensures \result == a[a.length - 2];
  @*/
    public static int penultimate(int[] a) {
    return a[a.length - 2];
    }

}
