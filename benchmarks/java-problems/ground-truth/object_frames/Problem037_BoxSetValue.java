public class Problem037_BoxSetValue {

    public static class Box { public int value; }


    /*@
  @ public normal_behavior
  @ requires box != null;
  @ assignable box.value;
  @ ensures box.value == v;
  @*/
    public static void setBox(Box box, int v) {
    box.value = v;
    }

}
