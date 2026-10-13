"""Deterministic synthetic fixtures, imported from the validated source."""
import datetime as dt, decimal
from collections import defaultdict
D=decimal.Decimal
decimal.getcontext().prec=70
SMALL_SCHEMA={
 'x_org':'id INT, parent_id INT, label VARCHAR(64)',
 'x_edges':'src INT, dst INT, weight DECIMAL(18,6)',
 'x_calendar':'day DATE, day_id INT',
 'x_targets':'region VARCHAR(32), month_id INT, target DECIMAL(24,6)',
}

SMALL_DATA={
 'x_org':[(i,None if i==1 else i//2,f'部门{i}') for i in range(1,128)],
 'x_edges':[(i,(i%12)+1,D('1.25')) for i in range(1,13)]+[(i,((i+3)%12)+1,D('0.75')) for i in range(1,13)],
 'x_calendar':[(dt.date(2025,1,1)+dt.timedelta(days=i),i+1) for i in range(365)],
 'x_targets':[(r,m,D(m*1000+(i+1)*17)) for i,r in enumerate(['华东','华南','EU','West']) for m in range(1,13)],
}
