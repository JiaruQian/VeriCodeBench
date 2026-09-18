public class Problem038_BoxNoMutationRead {

    public static class Box { public int value; }


    /*@
  @ public normal_behavior
  @ requires box != null;
  @ assignable \nothing;
  @ ensures \result == box.value;
  @*/
    public static int readBox(Box box) {
    return box.value;
    }

}
