public class Problem092_AsciiDigitCheck {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> ('0' <= ch && ch <= '9');
  @*/
    public static boolean isAsciiDigit(char ch) {
    return '0' <= ch && ch <= '9';
    }

}
