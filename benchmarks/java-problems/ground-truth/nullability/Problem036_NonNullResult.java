public class Problem036_NonNullResult {


    /*@
  @ public normal_behavior
  @ requires fallback != null;
  @ assignable \nothing;
  @ ensures \result != null;
  @ ensures s != null ==> \result == s;
  @ ensures s == null ==> \result == fallback;
  @*/
    public static String defaultString(String s, String fallback) {
    return s != null ? s : fallback;
    }

}
