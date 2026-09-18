public class Problem040_CounterDecrementIfPositive {

    public static class Counter {
        //@ public invariant value >= 0;
        public int value;
    }


    /*@
  @ public normal_behavior
  @ requires c != null;
  @ assignable c.value;
  @ ensures \old(c.value) > 0 ==> c.value == \old(c.value) - 1;
  @ ensures \old(c.value) == 0 ==> c.value == 0;
  @ ensures c.value >= 0;
  @*/
    public static void decrementIfPositive(Counter c) {
    if (c.value > 0) c.value = c.value - 1;
    }

}
