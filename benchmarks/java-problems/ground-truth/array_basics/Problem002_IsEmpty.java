public class Problem002_IsEmpty {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ assignable \nothing;
  @ ensures \result <==> a.length == 0;
  @*/
    public static boolean isEmpty(int[] a) {
    return a.length == 0;
    }

}
