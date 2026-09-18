public class Problem039_CounterIncrement {

    public static class Counter {
        //@ public invariant value >= 0;
        public int value;
    }


    /*@
  @ public normal_behavior
  @ requires c != null;
  @ requires c.value < Integer.MAX_VALUE;
  @ assignable c.value;
  @ ensures c.value == \old(c.value) + 1;
  @*/
    public static void increment(Counter c) {
    c.value = c.value + 1;
    }

}
