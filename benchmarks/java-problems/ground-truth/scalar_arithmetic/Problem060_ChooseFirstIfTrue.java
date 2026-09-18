public class Problem060_ChooseFirstIfTrue {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures flag ==> \result == x;
  @ ensures !flag ==> \result == y;
  @*/
    public static int choose(boolean flag, int x, int y) {
    return flag ? x : y;
    }

}
