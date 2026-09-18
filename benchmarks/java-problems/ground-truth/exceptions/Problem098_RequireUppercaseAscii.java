public class Problem098_RequireUppercaseAscii {


    /*@
  @ public normal_behavior
  @ requires 'A' <= ch && ch <= 'Z';
  @ assignable \nothing;
  @ ensures \result == ch;
  @ also
  @ public exceptional_behavior
  @ requires ch < 'A' || ch > 'Z';
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static char requireUpperAscii(char ch) {
    if (ch < 'A' || ch > 'Z') throw new IllegalArgumentException();
    return ch;
    }

}
