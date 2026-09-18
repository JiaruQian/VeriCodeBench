public class Problem044_DigitValueException {


    /*@
  @ public normal_behavior
  @ requires '0' <= ch && ch <= '9';
  @ assignable \nothing;
  @ ensures 0 <= \result && \result <= 9;
  @ ensures \result == ch - '0';
  @ also
  @ public exceptional_behavior
  @ requires ch < '0' || ch > '9';
  @ assignable \nothing;
  @ signals_only IllegalArgumentException;
  @ signals (IllegalArgumentException e) true;
  @*/
    public static int digitValue(char ch) {
    if (ch < '0' || ch > '9') throw new IllegalArgumentException();
    return ch - '0';
    }

}
