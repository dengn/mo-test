import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
R=ROOT.parent
created=json.loads((ROOT/'published.json').read_text());d=json.loads((ROOT/'validation.json').read_text());ddb=json.loads((R/'dolphindb-catalog.json').read_text());ops=json.loads((R/'operator-families.json').read_text());kernels=json.loads((R/'results/clickhouse-kernel-matrix.json').read_text());unmapped=[x['name'] for x in kernels if x['kind']=='public_frame_aggregate' and x['classification']=='no_direct_native_mapping'];assert len(unmapped)==175
named=[x['name'] for x in ddb['named_window_apis']];assert len(named)==152
special=[x['operator'] for x in ops if x['classification']=='no_one_to_one_specialized_kernel'];assert len(special)==65
body='''## Purpose and why this matters

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

'''
for x in created:body+=f"- [ ] #{x['number']} — {x['title'].removeprefix('[Feature Request]: ')}\n"
body+='''
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
SELECT id,COUNT(DISTINCT v) OVER(
  ORDER BY id ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
) result
FROM (
  SELECT 1 id,CAST(NULL AS DOUBLE) v
  UNION ALL SELECT 2,CAST(2 AS DOUBLE)
  UNION ALL SELECT 3,CAST(2 AS DOUBLE)
) fixture ORDER BY id;
```

The exact intended values for this smaller illustrative fixture are 0,1,1; the DISTINCT child contains the actually executed six-row fixture and full reference output. This compact illustration is not counted as another executed case.

The derivative correctness control uses the same three values/timestamps encoded through ClickHouse numbers/arrays; its UNION literal shape returned zeros and was not used as an oracle. No cross-engine throughput comparison or all-parameter parity is asserted.

## Coverage inventory: specialized DolphinDB families (65)

These families are covered by the operator requests above or require a documented migration/API contract before claiming equivalence:

```text
'''+', '.join(special)+'''
```

## Coverage inventory: named DolphinDB window interfaces (152)

These are namespace/API compatibility entries, including m/tm/cum variants of already available basic math. A SQL mapping/adapter may be preferable to introducing a duplicate native scalar function for every name:

```text
'''+', '.join(named)+'''
```

## Coverage inventory: additional ClickHouse kernel interfaces (175)

The registry inventory includes exact/approximate algorithms, weighted/multi-quantile variants, arrays, state/sequence and other-domain aggregates. Validate complete signatures, NULL/interpolation/state semantics and actual OVER support before declaring any native mapping equivalent. Name-absence probes alone do not establish mathematical inability:

```text
'''+', '.join(unmapped)+'''
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
'''
# Remove the non-executed compact illustration; every executable example in the issue should have a recorded run.
r=next(x for x in d['records'] if x['name']=='count_distinct' and x['repeat']==1)
start=body.index('```sql\nSELECT id,COUNT(DISTINCT v)');end=body.index('The derivative correctness control',start)
expected=', '.join('NULL' if x[-1] is None else str(int(x[-1])) for x in r['expected'])
body=body[:start]+'```sql\n'+r['sql']+';\n```\n\nThis actual six-row case was rejected 3/3; DuckDB returned exact intended values '+expected+'.\n\n'+body[end:]
payload=dict(key='roadmap',title='[Feature Request]: window analytics compatibility roadmap with validated ClickHouse/DolphinDB gaps',body=body)
(ROOT/'tracker-payload.json').write_text(json.dumps(payload,indent=2));(ROOT/'drafts/roadmap.md').write_text(body);print('Coverage tracker built',len(body),'chars; linked requests',len(created),'catalogs',len(named),len(unmapped))
if __name__=='__main__':pass
