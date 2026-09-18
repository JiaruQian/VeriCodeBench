public class Problem086_StringIsEmpty {


    /*@
  @ public normal_behavior
  @ requires s != null;
  @ assignable \nothing;
  @ ensures \result <==> s.length() == 0;
  @*/
    public static boolean stringIsEmpty(String s) {
    return s.length() == 0;
    }

}
