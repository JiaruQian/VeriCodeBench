public class Problem031_SumToN {


    /*@
  @ public normal_behavior
  @ requires 0 <= n && n <= 65535;
  @ assignable \nothing;
  @ ensures \result == n * (n + 1) / 2;
  @*/
    public static int sumToN(int n) {
    int s = 0;
    int i = 0;
    //@ loop_invariant 0 <= i && i <= n + 1;
    //@ loop_invariant s == i * (i - 1) / 2;
    //@ loop_assigns i, s;
    //@ decreases n + 1 - i;
    while (i <= n) {
        s += i;
        i++;
    }
    return s;
    }

}
