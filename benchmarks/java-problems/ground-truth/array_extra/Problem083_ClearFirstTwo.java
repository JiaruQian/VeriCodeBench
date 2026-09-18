public class Problem083_ClearFirstTwo {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length >= 2;
  @ assignable a[0], a[1];
  @ ensures a[0] == 0;
  @ ensures a[1] == 0;
  @*/
    public static void clearFirstTwo(int[] a) {
    a[0] = 0;
    a[1] = 0;
    }

}
