public class Problem041_PairSumReadonly {

    public static class Pair { public int left; public int right; }


    /*@
  @ public normal_behavior
  @ requires p != null;
  @ requires Integer.MIN_VALUE <= (long)p.left + (long)p.right && (long)p.left + (long)p.right <= Integer.MAX_VALUE;
  @ assignable \nothing;
  @ ensures \result == p.left + p.right;
  @*/
    public static int sumPair(Pair p) {
    return p.left + p.right;
    }

}
