public class Problem069_SecondElement {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable \nothing;
  @ ensures \result == a[1];
  @*/
    public static int second(int[] a) {
    return a[1];
    }

}
