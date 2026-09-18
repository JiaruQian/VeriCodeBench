public class Problem095_CheckedCharAt {


    /*@
  @ public normal_behavior
  @ requires s != null && 0 <= i && i < s.length();
  @ assignable \nothing;
  @ ensures \result == s.charAt(i);
  @ also
  @ public exceptional_behavior
  @ requires s == null || i < 0 || (s != null && i >= s.length());
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static char checkedCharAt(String s, int i) {
    if (s == null || i < 0 || i >= s.length()) throw new IllegalArgumentException();
    return s.charAt(i);
    }

}
