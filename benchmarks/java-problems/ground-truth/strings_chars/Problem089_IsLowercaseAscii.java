public class Problem089_IsLowercaseAscii {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> ('a' <= ch && ch <= 'z');
  @*/
    public static boolean isLowerAscii(char ch) {
    return 'a' <= ch && ch <= 'z';
    }

}
