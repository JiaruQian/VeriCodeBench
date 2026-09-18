public class Problem042_RangeContains {

    public static class Range {
        //@ public invariant low <= high;
        public int low;
        public int high;
    }


    /*@
  @ public normal_behavior
  @ requires r != null;
  @ assignable \nothing;
  @ ensures \result <==> (r.low <= x && x <= r.high);
  @*/
    public static boolean contains(Range r, int x) {
    return r.low <= x && x <= r.high;
    }

}
