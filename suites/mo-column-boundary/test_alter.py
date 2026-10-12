#!/usr/bin/env python3
"""Compare CREATE and ALTER boundary behavior with/without a primary key."""
import json
import threading
from types import SimpleNamespace
import test_columns as probe


def main():
    probe.ARGS = SimpleNamespace(deadline=120)
    db = 'column_boundary_20261012'
    c = probe.conn(db, 150)
    thread = threading.Thread(target=probe.monitor, daemon=True)
    thread.start()
    records = []
    try:
        for pk, sizes in ((True, (4095, 4096, 4097)),
                          (False, (4094, 4095, 4096, 4097))):
            for n in sizes:
                name = f'alter_{n}_' + ('pk' if pk else 'nopk')
                prefix = name
                defs = [col + ' int' + (' primary key' if pk and i == 0 else '')
                        for i, col in enumerate(probe.columns(n))]
                create = probe.run_step(c, prefix + '_create',
                                        f'create table {name}(' + ','.join(defs) + ')')
                steps = [create]
                if create['status'] == 'success':
                    for extra in ('extra_a', 'extra_b'):
                        steps.append(probe.run_step(c, prefix + '_' + extra,
                                                    f'alter table {name} add column {extra} int'))
                        steps.append(probe.run_step(c, prefix + '_' + extra + '_metadata',
                            'select count(*) from information_schema.columns '
                            f"where table_schema='{db}' and table_name='{name}'"))
                records.append({'initial_columns': n, 'primary_key': pk, 'table': name, 'steps': steps})
                (probe.P / 'alter-results.json').write_text(json.dumps(records, indent=2, default=str))
        # Batch ADD crossing the threshold must be atomic if it is rejected.
        name = 'alter_multi_pk'
        defs = [col + ' int' + (' primary key' if i == 0 else '')
                for i, col in enumerate(probe.columns(4095))]
        steps = [probe.run_step(c, name + '_create',
                               f'create table {name}(' + ','.join(defs) + ')')]
        steps.append(probe.run_step(c, name + '_add_two',
                                   f'alter table {name} add column extra_a int, add column extra_b int'))
        steps.append(probe.run_step(c, name + '_metadata',
            'select count(*) from information_schema.columns '
            f"where table_schema='{db}' and table_name='{name}'"))
        records.append({'initial_columns': 4095, 'primary_key': True,
                        'table': name, 'steps': steps})
        (probe.P / 'alter-results.json').write_text(json.dumps(records, indent=2, default=str))
    finally:
        c.close()
        probe.STOP.set()
        thread.join(8)


if __name__ == '__main__':
    main()
