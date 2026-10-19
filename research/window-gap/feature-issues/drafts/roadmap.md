## Purpose and why this matters

Track the verified MatrixOne window-analysis gaps needed by time-series, risk, telemetry and data-science pipelines. Users need peer-aware baselines, sparse-observation navigation, exact rolling uniqueness, weighted/pairwise statistics, local TopN/rank, decay and technical indicators without reimplementing every contract in client code.

This is a coordination roadmap. The individual requests below contain self-contained synthetic SQL, actual rejection results, independently calculated expected outputs, working alternatives and concrete use cases. It does not request hundreds of redundant issues for aliases or estimator variants.

## Scope and counting rules

Tested MatrixOne commit: `23d8f61252f3017dff218b530817a240206fd762`. ClickHouse reference: 26.9.16.11. DolphinDB basis: official documentation; no DolphinDB server/performance test is claimed.

| Catalog | Counterpart scope | MO mapping / gap |
|---|---:|---|
| ClickHouse documented window entries | 14 | 11 implemented entries; 3 dedicated entries absent |
| DolphinDB SQL OVER primitives | 39 | 22 native mappings; 17 dedicated primitives absent |
| DolphinDB m/tm/cum/TopN/TA/EWM named interfaces | 152 | same-name API entries unavailable; basic SQL math can still be available |
| Prefix-normalized DolphinDB operator families | 78 | 13 basic native-kernel families; 65 lack a validated one-to-one specialized mapping |
| Canonical public ClickHouse aggregate-kernel catalog | 191 | 16 explicit native candidates; 175 candidate interfaces without a validated one-to-one native mapping |

These counts **must not be added**. They overlap and distinguish API names, algorithms/state variants, accepted SQL syntax and mathematical computability. The 175 entry count is **not** 175 impossible business calculations. The ClickHouse registry inventory was not a full-signature functional window test of every kernel. MO already has ordinary max_by/any_value, standard windows, MEDIAN/PERCENTILE_CONT, approximate distinct primitives and native INTERVAL/SLIDING/FILL; those are not being requested as missing overall capabilities.

All 17 declared common mathematical profiles were recomputed using existing MO SQL and independently checked with NumPy/SciPy. A missing dedicated entry therefore does not establish inability to calculate that profile or worse performance.

## Actionable requests with validation cases

- [ ] #29931 — GROUPS window frames for peer-aware time-series analysis
- [ ] #29932 — EXCLUDE frame clauses for leave-one-out and peer-excluded analytics
- [ ] #29933 — IGNORE NULLS and non-NULL value navigation in windows
- [ ] #29934 — DISTINCT window aggregates for exact rolling unique metrics
- [ ] #29935 — FILTER clauses on aggregates and window aggregates
- [ ] #29936 — frame-respecting lagInFrame and leadInFrame navigation
- [ ] #29937 — non-negative time derivatives for irregular cumulative counters
- [ ] #29938 — native weighted sum and average aggregates with window support
- [ ] #29939 — native correlation and covariance aggregates with window support
- [ ] #29940 — sum2, skewness and kurtosis aggregate/window primitives
- [ ] #29941 — product aggregates with window support and zero/sign/NULL semantics
- [ ] #29942 — extrema positions within sliding frames with deterministic ties
- [ ] #29943 — allow max_by and any_value aggregates to compose with OVER
- [ ] #29944 — native exact weighted percentiles with window support
- [ ] #29945 — exponential-weighted statistics with explicit decay and NULL policies
- [ ] #29946 — bounded TopN-by-key window statistics with deterministic ties
- [ ] #29947 — local sliding-window ranks distinct from partition-wide RANK
- [ ] #29948 — valid-observation windows and reset-aware cumulative state
- [ ] #29949 — technical-indicator kernels and rolling risk analytics

- [ ] #10182 — Existing native regression request; a fresh comment adds REGR_SLOPE/INTERCEPT aggregate/window rejection cases, slope use cases and a complete-value-verified SQL control.
- #29925 — Separate execution bug: untyped NULL defaults panic; typed NULL returns wrong zero. Do not count LAG/LEAD as unimplemented functions or propose typed NULL as a correct workaround.

Completed older work such as #28031 (RESPECT NULLS), #27342 (BIT_XOR OVER), #27064 (tumbling max_by arity) and #27352 (bounded-frame SUM performance) is not silently reopened. New requests distinguish currently rejected syntax/entries from those older contracts.

## Concrete test evidence and boundaries

The new read-only matrix executed 297 MO queries: 240 expected syntax/entry rejections and 57 successfully executed controls with checked output values. Each listed small case has three executions. The independent references include DuckDB window semantics, NumPy/SciPy math, four live ClickHouse controls and a complete ten-row/17-column MO rewrite. Subsequent SELECT 1 succeeded.

Example dedicated-interface name probe (executed 3/3, error 20105):

```sql
SELECT ewmMean(CAST(1 AS DOUBLE),3) result;
```

This demonstrates unavailable **name resolution**; it is not a valid-signature claim about DolphinDB ewmMean or a complete algorithm-equivalence test. The EWM child request supplies a separately verified alpha=0.5/adjust=False business profile and SQL alternative.

Example real window-syntax failure (executed 3/3, error 20102):

```sql
SELECT id,COUNT(DISTINCT v) OVER(PARTITION BY gid ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) result FROM (SELECT 1 id,1 gid,0 tick,CAST(NULL AS DOUBLE) v,CAST(2.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag UNION ALL SELECT 2 id,1 gid,0 tick,CAST(2.0 AS DOUBLE) v,CAST(4.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,0 flag UNION ALL SELECT 3 id,1 gid,1 tick,CAST(4.0 AS DOUBLE) v,CAST(3.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,1 flag UNION ALL SELECT 4 id,1 gid,3 tick,CAST(4.0 AS DOUBLE) v,CAST(7.0 AS DOUBLE) y,CAST(3.0 AS DOUBLE) w,1 flag UNION ALL SELECT 5 id,1 gid,3 tick,CAST(NULL AS DOUBLE) v,CAST(5.0 AS DOUBLE) y,CAST(1.0 AS DOUBLE) w,0 flag UNION ALL SELECT 6 id,1 gid,8 tick,CAST(-1.0 AS DOUBLE) v,CAST(8.0 AS DOUBLE) y,CAST(2.0 AS DOUBLE) w,1 flag) fixture ORDER BY id;
```

This actual six-row case was rejected 3/3; DuckDB returned exact intended values 0, 1, 2, 2, 1, 2.

The derivative correctness control uses the same three values/timestamps encoded through ClickHouse numbers/arrays; its UNION literal shape returned zeros and was not used as an oracle. No cross-engine throughput comparison or all-parameter parity is asserted.

## Coverage inventory: specialized DolphinDB families (65)

These families are covered by the operator requests above or require a documented migration/API contract before claiming equivalence:

```text
LowRange, PositiveStreak, TopRange, avgTopN, beta, betaTopN, corr, corrTopN, covar, covarTopN, covarp, covarpTopN, dema, dynamicGroupCumcount, dynamicGroupCumsum, ema, ewmCorr, ewmCov, ewmMean, ewmStd, ewmVar, firstNot, gema, ifirstNot, ilastNot, imax, imaxLast, imin, iminLast, kama, kurtosis, kurtosisTopN, lastNot, linearTimeTrend, ma, mad, maxDrawdown, maxPositiveStreak, movingTopNIndex, movingWindowIndex, mse, nunique, percentileTopN, prod, rank, skew, skewTopN, slr, sma, stdTopN, stdpTopN, sum2, sum3, sum4, sumTopN, t3, tema, trima, varTopN, varpTopN, wavg, wilder, wma, wsum, wsumTopN
```

## Coverage inventory: named DolphinDB window interfaces (152)

These are namespace/API compatibility entries, including m/tm/cum variants of already available basic math. A SQL mapping/adapter may be preferable to introducing a duplicate native scalar function for every name:

```text
cumPositiveStreak, cumavg, cumavgTopN, cumbeta, cumbetaTopN, cumcorr, cumcorrTopN, cumcount, cumcovar, cumcovarTopN, cumcovarp, cumcovarpTopN, cumfirstNot, cumkurtosisTopN, cumlastNot, cummax, cummed, cummin, cumnunique, cumpercentile, cumprod, cumrank, cumskewTopN, cumstd, cumstdTopN, cumstdp, cumstdpTopN, cumsum, cumsum2, cumsum3, cumsum4, cumsumTopN, cumvar, cumvarTopN, cumvarp, cumvarpTopN, cumwavg, cumwsum, cumwsumTopN, dema, dynamicGroupCumcount, dynamicGroupCumsum, ema, ewmCorr, ewmCov, ewmMean, ewmStd, ewmVar, gema, kama, linearTimeTrend, mLowRange, mTopRange, ma, mavg, mavgTopN, mbeta, mbetaTopN, mcorr, mcorrTopN, mcount, mcovar, mcovarTopN, mcovarp, mcovarpTopN, mfirst, mfirstNot, mifirstNot, milastNot, mimax, mimaxLast, mimin, miminLast, mkurtosis, mkurtosisTopN, mlast, mlastNot, mmad, mmax, mmaxDrawdown, mmaxPositiveStreak, mmed, mmin, mmse, movingTopNIndex, movingWindowIndex, mpercentile, mpercentileTopN, mprod, mrank, mskew, mskewTopN, mslr, mstd, mstdTopN, mstdp, mstdpTopN, msum, msum2, msumTopN, mvar, mvarTopN, mvarp, mvarpTopN, mwavg, mwsum, mwsumTopN, sma, t3, tema, tmLowRange, tmTopRange, tmavg, tmavgTopN, tmbeta, tmbetaTopN, tmcorr, tmcorrTopN, tmcount, tmcovar, tmcovarTopN, tmcovarp, tmcovarpTopN, tmfirst, tmkurtosis, tmkurtosisTopN, tmlast, tmmax, tmmed, tmmin, tmpercentile, tmprod, tmrank, tmskew, tmskewTopN, tmstd, tmstdTopN, tmstdp, tmstdpTopN, tmsum, tmsum2, tmsumTopN, tmvar, tmvarTopN, tmvarp, tmvarpTopN, tmwavg, tmwsum, tmwsumTopN, trima, wilder, wma
```

## Coverage inventory: additional ClickHouse kernel interfaces (175)

The registry inventory includes exact/approximate algorithms, weighted/multi-quantile variants, arrays, state/sequence and other-domain aggregates. Validate complete signatures, NULL/interpolation/state semantics and actual OVER support before declaring any native mapping equivalent. Name-absence probes alone do not establish mathematical inability:

```text
MVTEncode, analysisOfVariance, any, anyHeavy, anyLast, approx_top_k, approx_top_sum, argAndMax, argAndMin, argMax, argMin, avgWeighted, boundingRatio, categoricalInformationValue, contingency, corr, corrMatrix, corrStable, covarPop, covarPopMatrix, covarPopStable, covarSamp, covarSampMatrix, covarSampStable, cramersV, cramersVBiasCorrected, deltaSum, deltaSumTimestamp, distinctDynamicTypes, distinctJSONPaths, distinctJSONPathsAndTypes, entropy, estimateCompressionRatio, exponentialMovingAverage, exponentialTimeDecayedAvg, exponentialTimeDecayedCount, exponentialTimeDecayedMax, exponentialTimeDecayedSum, flameGraph, gini, groupArray, groupArrayInsertAt, groupArrayIntersect, groupArrayLast, groupArrayMovingAvg, groupArrayMovingSum, groupArraySample, groupArraySorted, groupBitmap, groupBitmapAnd, groupBitmapOr, groupBitmapXor, groupFormat, groupNumericIndexedVector, groupUniqArray, hierarchicalKMeans, histogram, intervalLengthSum, kolmogorovSmirnovTest, kurtPop, kurtSamp, largestTriangleThreeBuckets, mannWhitneyUTest, maxIntersections, maxIntersectionsPosition, maxMappedArrays, meanZTest, mergedJSONPatch, minMappedArrays, quantile, quantileBFloat16, quantileBFloat16Weighted, quantileDD, quantileDeterministic, quantileExact, quantileExactExclusive, quantileExactHigh, quantileExactLow, quantileExactWeighted, quantileExactWeightedInterpolated, quantileGK, quantileInterpolatedWeighted, quantilePrometheusHistogram, quantileTDigest, quantileTDigestWeighted, quantileTiming, quantileTimingWeighted, quantiles, quantilesBFloat16, quantilesBFloat16Weighted, quantilesDD, quantilesDeterministic, quantilesExact, quantilesExactExclusive, quantilesExactHigh, quantilesExactInclusive, quantilesExactLow, quantilesExactWeighted, quantilesExactWeightedInterpolated, quantilesGK, quantilesInterpolatedWeighted, quantilesPrometheusHistogram, quantilesTDigest, quantilesTDigestWeighted, quantilesTiming, quantilesTimingWeighted, rankCorr, regr_avgx, regr_avgy, regr_count, regr_intercept, regr_r2, regr_slope, regr_sxx, regr_sxy, regr_syy, retention, sequenceCount, sequenceMatch, sequenceMatchEvents, sequenceNextNode, simpleLinearRegression, singleValueOrNull, skewPop, skewSamp, sparkbar, stddevPopStable, stddevSampStable, stochasticLinearRegression, stochasticLogisticRegression, studentTTest, studentTTestOneSample, sumCount, sumKahan, sumMapFiltered, sumMapFilteredWithOverflow, sumMapWithOverflow, sumMappedArrays, sumWithOverflow, theilsU, timeSeriesAvgToGrid, timeSeriesBottomKMasks, timeSeriesChangesToGrid, timeSeriesCountToGrid, timeSeriesDeltaToGrid, timeSeriesDerivToGrid, timeSeriesGroupArray, timeSeriesIncreaseToGrid, timeSeriesInstantDeltaToGrid, timeSeriesInstantRateToGrid, timeSeriesLastTwoSamples, timeSeriesLimitKMasks, timeSeriesMaxToGrid, timeSeriesMinToGrid, timeSeriesPredictLinearToGrid, timeSeriesRateToGrid, timeSeriesResampleToGridWithStaleness, timeSeriesResetsToGrid, timeSeriesSumToGrid, timeSeriesTimestampOfMaxToGrid, timeSeriesTimestampOfMinToGrid, timeSeriesTopKMasks, topK, topKWeighted, uniq, uniqCombined, uniqCombined64, uniqExact, uniqHLL12, uniqTheta, uniqUpTo, varPopStable, varSampStable, welchTTest, windowFunnel
```

## Acceptance approach

1. Land the semantic/operator requests with deterministic complete-output/NULL-bit tests and explicit supported conventions.
2. Publish migration mappings that distinguish exact native equivalence, verified SQL composition, approximate alternatives and unsupported parameter/state contracts.
3. Use paired correctness-preserving benchmarks before claiming a native incremental-state speedup; don't infer performance from the name count.
4. Keep individual operator issues independently reviewable; update this checklist as actual support is verified rather than treating a closed historical issue as proof of all-version parity.

## Official sources

- https://clickhouse.com/docs/reference/functions/window-functions
- https://clickhouse.com/docs/reference/aggregate-functions/reference
- https://docs.dolphindb.com/en/Programming/SQLStatements/analytic_functions.html
- https://docs.dolphindb.com/en/Functions/Themes/mFunctions.html
- https://docs.dolphindb.com/en/Functions/Themes/tmFunctions.html
- https://docs.dolphindb.com/en/Functions/Themes/cumFunctions.html
- https://docs.dolphindb.com/en/Functions/Themes/mTopN.html
