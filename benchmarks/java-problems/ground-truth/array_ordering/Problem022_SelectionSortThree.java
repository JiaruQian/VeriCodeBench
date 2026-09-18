public class Problem022_SelectionSortThree {


    /*@
  @ public normal_behavior
  @ requires a != null;
  @ requires a.length == 3;
  @ assignable a[0], a[1], a[2];
  @ ensures a[0] <= a[1] && a[1] <= a[2];
  @ ensures a[0] + a[1] + a[2] == \old(a[0]) + \old(a[1]) + \old(a[2]);
  @*/
    public static void sort3(int[] a) {
    if (a[0] > a[1]) { int t = a[0]; a[0] = a[1]; a[1] = t; }
    if (a[1] > a[2]) { int t = a[1]; a[1] = a[2]; a[2] = t; }
    if (a[0] > a[1]) { int t = a[0]; a[0] = a[1]; a[1] = t; }
    }

}
