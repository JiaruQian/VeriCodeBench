public class Problem090_IsUppercaseAscii {


    /*@
  @ public normal_behavior
  @ assignable \nothing;
  @ ensures \result <==> ('A' <= ch && ch <= 'Z');
  @*/
    public static boolean isUpperAscii(char ch) {
    return 'A' <= ch && ch <= 'Z';
    }

}
