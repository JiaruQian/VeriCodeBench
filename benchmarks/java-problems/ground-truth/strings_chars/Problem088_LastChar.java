public class Problem088_LastChar {


    /*@
  @ public normal_behavior
  @ requires s != null;
  @ requires s.length() > 0;
  @ assignable \nothing;
  @ ensures \result == s.charAt(s.length() - 1);
  @*/
    public static char lastChar(String s) {
    return s.charAt(s.length() - 1);
    }

}
