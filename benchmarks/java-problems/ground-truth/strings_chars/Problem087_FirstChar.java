public class Problem087_FirstChar {


    /*@
  @ public normal_behavior
  @ requires s != null;
  @ requires s.length() > 0;
  @ assignable \nothing;
  @ ensures \result == s.charAt(0);
  @*/
    public static char firstChar(String s) {
    return s.charAt(0);
    }

}
