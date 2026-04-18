# Example: a failing Fibonacci implementation

A tiny task to smoke-test the harness end-to-end. The starter code has
a test that pins the recurrence's behaviour for `n=0` and `n=10`, plus
an implementation that is deliberately wrong (`fib(0) == 1` instead of
`0`).

Run the harness against it:

```bash
cd examples/fibonacci
git init -q && git add -A && git commit -q -m seed
cp ../../.harness/gate.sh .harness/gate.sh  # or keep the local one
python -m harness "fix fib() so the existing tests pass"
```

Expect the loop to:

1. Round 1 coder: reads `fib.py` + `test_fib.py`, flips the base case.
2. Round 1 gate: pytest passes → reviewer runs.
3. Round 1 reviewer: no blocker/major → PASS, confidence=high.
