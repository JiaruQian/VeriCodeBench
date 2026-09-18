public class Problem091_AsciiToLower {


    /*@
  @ public normal_behavior
  @ requires 'A' <= ch && ch <= 'Z';
  @ assignable \nothing;
  @ ensures \result == ch + ('a' - 'A');
  @*/
    public static char toLowerAscii(char ch) {
    return (char)(ch + ('a' - 'A'));
    }

}
