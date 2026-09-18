public class Problem043_FrameTwoBoxes {

    public static class Box { public int value; }


    /*@
  @ public normal_behavior
  @ requires a != null && b != null;
  @ requires a != b;
  @ assignable a.value;
  @ ensures a.value == v;
  @ ensures b.value == \old(b.value);
  @*/
    public static void updateFirst(Box a, Box b, int v) {
    a.value = v;
    }

}
