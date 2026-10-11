### Summary

Please add SQL `TANH(x)` support for scientific feature transformations and SQL analytics. Currently even constant inputs are rejected:

```sql
SELECT TANH(0.0);
SELECT TANH(1.0);
-- ERROR 20105: not supported: function or operator 'tanh'
```

This is a **function support request**, not a wrong-result report. NumPy/Pandas can compute tanh on the client, but pushing a transformed aggregate into MatrixOne currently requires rewriting the SQL.

### Reproduction with analytical data

```sql
CREATE DATABASE IF NOT EXISTS tanh_feature_repro;
USE tanh_feature_repro;
CREATE TABLE tanh_input (id INT PRIMARY KEY, x DOUBLE);
INSERT INTO tanh_input VALUES (1,-2.0),(2,-1.0),(3,0.0),(4,1.0),(5,2.0),(6,NULL);

SELECT id,TANH(x) FROM tanh_input ORDER BY id;
SELECT COUNT(TANH(x)),AVG(TANH(x)) FROM tanh_input;
-- Actual: ERROR 20105, function or operator 'tanh' not supported.
```

Expected numerical values for the non-null rows, from NumPy:
`[-0.9640275800758169, -0.7615941559557649, 0.0, 0.7615941559557649, 0.9640275800758169]`.
The NULL input should produce NULL; the aggregate should return count 5 and average approximately 0.

### Evidence and impact

Fresh verification on 2026-10-11 reproduced the error for `TANH(0.0)` and `TANH(1.0)`.

In a 100,000-case data-science compatibility suite, 1,000 parameterized TANH aggregates were executed through Pandas/SQLAlchemy and another 1,000 through PyMySQL with a NumPy result oracle. All 2,000 statements failed with this same unsupported-function error. These are **2,000 affected cases from one missing function**, not separate defects.

Representative failed query:

```sql
SELECT AVG(TANH(x/100)) AS v
FROM ds
WHERE id>=966 AND id<1768 AND g=2;
```

### Current bounded-input workaround

For the bounded inputs used in the test, this rewrite was verified:

```sql
SELECT (EXP(2*x)-1)/(EXP(2*x)+1) FROM tanh_input;
```

That expression is **not a general replacement**: large positive x can overflow EXP, and very small x can lose precision through subtraction. A native implementation should use numerically stable tanh behavior rather than this expression.

### Suggested coverage

- `TANH(0)=0`, positive/negative symmetry, values ±1 and ±2.
- NULL propagation and aggregate use.
- Small-magnitude inputs around zero.
- Large finite magnitudes approaching ±1 without EXP overflow.
- Floating-point tolerance compared against a trusted tanh implementation.

### Existing issue search

Repository-wide issue searches for `tanh` found no direct issue at filing time. #2094 (SINH) and #2095 (COSH) are related historical function-support work, but do not cover TANH.

### Environment

- Executed mo-service build commit: `23d8f61252f3017dff218b530817a240206fd762` (binary build metadata).
- `SELECT VERSION()`: `8.0.30-MatrixOne-v`
- Pandas 2.2.3, NumPy 2.1.3, SQLAlchemy 2.0.43, PyMySQL 1.2.0, Python 3.12.
- Dedicated local synthetic-data instance.

