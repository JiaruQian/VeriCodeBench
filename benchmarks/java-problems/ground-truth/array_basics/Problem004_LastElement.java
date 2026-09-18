public class Problem004_LastElement {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length > 0;
  @ assignable \nothing;
  @ ensures \result == a[a.length - 1];
  @*/
    public static int last(int[] a) {
    return a[a.length - 1];
    }

}
