"""Derive review classifications without modifying raw differential results."""
from pathlib import Path
import collections
import csv
import json
import re

P = Path(__file__).resolve().parent
def load(name):
    return [json.loads(line) for line in (P / name).read_text().splitlines() if line]

def classify(r):
    s, f, feature = r['status'], r.get('function'), r['feature']
    err = (r.get('mo_error') or {}).get('message', '')
    if s.startswith('pass'):
        return s, None
    if s == 'documented_semantic_difference':
        return 'sphere_vs_ellipsoid_semantics', None
    if s == 'reference_rejected':
        return 'api_dialect_difference', None
    if s == 'feature_probe_review':
        return 'invalid_reference_probe_corrected_in_supplement', None
    if s == 'verified_feature_gap':
        return 'feature_gap', None
    if s == 'rejection_difference':
        if r['mo_error']:
            return 'finite_coordinate_admission_policy', None
        return 'confirmed_mo_defect', 'MO-GIS-003'
    if s == 'mo_execution_error':
        if 'GEOMETRY32' in err:
            return 'geometry32_overload_gap', None
        if 'gnomonic hemisphere' in err:
            return 'documented_geodetic_topology_domain_limit', None
        if 'max_points_in_geometry' in err:
            return 'configurable_vertex_budget', None
        if 'nesting depth' in err:
            return 'collection_depth_budget', None
        if f == 'st_isvalid' and 'not supported' in err:
            return 'compound_validity_feature_gap', None
    if s == 'candidate_difference':
        if f in ('st_aswkb', 'st_asbinary'):
            return 'empty_point_nan_encoding_difference', None
        if f in ('st_dimension', 'st_numgeometries') or (f == 'st_isvalid' and 'empty' in feature):
            return 'empty_geometry_semantic_difference', None
        if f == 'st_isvalid' and 'duplicate' in feature:
            return 'confirmed_mo_defect', 'MO-GIS-002'
        if f == 'st_isvalid' and 'tiny' in feature:
            return 'mysql_compatible_numeric_validity_policy', None
        if f == 'st_issimple' and 'duplicate' in feature:
            return 'mysql_compatible_simplicity_difference', None
        if f == 'st_issimple' and 'tiny' in feature:
            return 'numeric_robustness_candidate_not_counted_confirmed', None
        if f == 'st_intersection':
            return 'confirmed_mo_defect', 'MO-GIS-001'
        if f == 'st_area':
            return 'reference_side_spherical_area_anomaly', 'PG-GIS-001'
    raise ValueError(('Unreviewed result', r))

def main():
    raw_counts = {}
    records = []
    all_cases = {}
    for case_file, result_file in [('cases.jsonl','results.jsonl'), ('supplement-cases.jsonl','supplement-results.jsonl')]:
        cases = {c['id']:c for c in load(case_file)}
        results = load(result_file)
        assert len(cases) == len(results) == len({r['id'] for r in results})
        assert set(cases) == {r['id'] for r in results}
        all_cases.update(cases)
        raw_counts[result_file] = dict(collections.Counter(r['status'] for r in results))
        for r in results:
            category, issue = classify(r)
            records.append(dict(r, suite=result_file, classification=category, finding_id=issue))
    with (P / 'classified-results.jsonl').open('w') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False)+'\n')
    summary = {'total_differential_cases':len(records), 'raw_counts':raw_counts,
               'review_counts':dict(collections.Counter(r['classification'] for r in records)),
               'confirmed_mo_defect_groups':3,
               'findings_cases':dict(collections.Counter(r['finding_id'] for r in records if r['finding_id'])),
               'unclassified':0}
    (P / 'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    mo = json.loads((P / 'mo-functions.json').read_text())
    by_fn = collections.defaultdict(list)
    for r in records:
        by_fn[r.get('function')].append(r)
    with (P / 'mo-function-matrix.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['name','canonical_id','cases','classifications'])
        for name, canonical in sorted(mo.items()):
            rs = by_fn[name]
            assert rs, name
            writer.writerow([name, canonical,len(rs),json.dumps(dict(collections.Counter(r['classification'] for r in rs)))])
    pg = json.loads((P / 'postgis-functions.json').read_text())
    pg_names_used = collections.Counter()
    for c in all_cases.values():
        for name in re.findall(r'\b(st_[a-z0-9_]+)\s*\(', (c.get('pg_sql') or '').lower()):
            pg_names_used[name] += 1
    with (P / 'postgis-catalog-matrix.csv').open('w') as f:
        writer = csv.writer(f)
        writer.writerow(['name','arguments','return_type','mo_same_name_registered','differential_sql_mentions','coverage_scope'])
        for name, args, ret in pg:
            writer.writerow([name,args,ret,name in mo,pg_names_used[name],
                             'sampled_by_name_not_all_overloads' if pg_names_used[name] else 'catalogued_not_exhaustively_executed'])
    apps = json.loads((P / 'application-results.json').read_text())
    aliases = {
        'nearby_recheck_with_stable_round12_ties':'nearby_radius_and_nearest_points',
        'nearby_final_recheck_stable_decimal12_order':'nearby_radius_and_nearest_points',
        'geojson_exchange_recheck_with_geometry_comparison':'wkb_geojson_csv_exchange',
    }
    latest = {aliases.get(r['feature'],r['feature']):dict(r,workflow=aliases.get(r['feature'],r['feature'])) for r in apps}
    assert len(latest) == 9 and all(r['status']=='pass' for r in latest.values())
    (P / 'application-final-results.json').write_text(json.dumps(list(latest.values()),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__ == '__main__':
    main()
