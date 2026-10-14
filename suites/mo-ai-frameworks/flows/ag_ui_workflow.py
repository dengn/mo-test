import json,hashlib
from pathlib import Path
from pydantic import ValidationError
from ag_ui import core
from ag_ui.encoder import EventEncoder
from adapters.ag_ui_journal import MatrixOneAGUIJournal,VALIDATE

class NativeEncodedJournal:

    def __init__(self, directory, tenant):
        self.directory = Path(directory)
        self.tenant = tenant

    def _path(self, run_id):
        return self.directory / (hashlib.sha256((self.tenant + '\x00' + run_id).encode()).hexdigest() + '.jsonl')

    def append_batch(self, run_id, events):
        encoded = [EventEncoder().encode(VALIDATE.validate_python(e)) for e in events]
        with self._path(run_id).open('a') as file:
            for wire in encoded:
                file.write(json.dumps(wire, ensure_ascii=False) + '\n')

    def replay(self, run_id, after_id=0):
        path = self._path(run_id)
        if not path.exists():
            return []
        result = []
        for index, line in enumerate(path.read_text().splitlines(), 1):
            if index > after_id:
                result.append((index, decode_wire(json.loads(line))))
        return result

    def delete(self, run_id):
        self._path(run_id).unlink(missing_ok=True)

def decode_wire(wire):
    data = '\n'.join((line[6:] for line in wire.splitlines() if line.startswith('data: ')))
    assert data, 'No native SSE data payload'
    return VALIDATE.validate_json(data)

def event_lifecycle(factory):
    events = [core.RunStartedEvent(thread_id='thread_a', run_id='run_a'), core.TextMessageStartEvent(message_id='m1', role='assistant'), core.TextMessageContentEvent(message_id='m1', delta='alpha '), core.TextMessageContentEvent(message_id='m1', delta='中文'), core.TextMessageEndEvent(message_id='m1'), core.ToolCallStartEvent(tool_call_id='c1', tool_call_name='retrieve', parent_message_id='m1'), core.ToolCallArgsEvent(tool_call_id='c1', delta='{"tenant":"a"}'), core.ToolCallEndEvent(tool_call_id='c1'), core.ToolCallResultEvent(message_id='m2', tool_call_id='c1', content='[{"id":1,"text":"中文"}]', role='tool'), core.StateSnapshotEvent(snapshot={'count': 1, 'flags': [True, None], 'text': '中文', 'nested': {'number': 2.5}}), core.RunFinishedEvent(thread_id='thread_a', run_id='run_a', result={'answer': 'alpha 中文'})]
    expected = [event.model_dump(mode='json', by_alias=True, exclude_none=True) for event in events]
    encoder = EventEncoder()
    for event, data in zip(events, expected):
        assert decode_wire(encoder.encode(event)).model_dump(mode='json', by_alias=True, exclude_none=True) == data
    factory('a').append_batch('run_a', events[:5])
    prefix = factory('a').replay('run_a')
    cursor = prefix[-1][0]
    factory('a').append_batch('run_a', events[5:])
    all_events = factory('a').replay('run_a')
    assert [e.model_dump(mode='json', by_alias=True, exclude_none=True) for _, e in all_events] == expected
    suffix = factory('a').replay('run_a', cursor)
    assert [e.type for _, e in suffix] == [e.type for e in events[5:]]
    assert len({i for i, _ in all_events}) == len(events)
    replayed = all_events
    assert ''.join((e.delta for _, e in replayed if isinstance(e, core.TextMessageContentEvent))) == 'alpha 中文'
    assert next((e for _, e in replayed if isinstance(e, core.ToolCallResultEvent))).tool_call_id == 'c1'
    assert next((e for _, e in replayed if isinstance(e, core.StateSnapshotEvent))).snapshot == events[-2].snapshot
    factory('b').append_batch('run_a', [core.RunStartedEvent(thread_id='thread_b', run_id='run_a')])
    assert len(factory('b').replay('run_a')) == 1
    assert factory("a' OR 1=1 --").replay('run_a') == []
    assert factory('a').replay("run_a' OR 1=1 --") == []
    assert factory('a').replay('missing') == []
    before = len(factory('a').replay('run_a'))
    for invalid in [{'type': 'TEXT_MESSAGE_CONTENT', 'messageId': 'm1'}, {'type': 'NOT_AN_EVENT'}]:
        try:
            factory('a').append_batch('run_a', [events[0], invalid])
        except ValidationError:
            pass
        else:
            raise AssertionError('Invalid protocol event silently accepted')
        assert len(factory('a').replay('run_a')) == before
    factory('a').delete('run_a')
    assert factory('a').replay('run_a') == []
    assert len(factory('b').replay('run_a')) == 1
    return 'native AG-UI typed events/EventEncoder SSE roundtrip, 11-event ordered journal/reopen/cursor resume; message deltas/tool correlation/nested state preserved; tenant/run isolation, mixed invalid batch rejected atomically, delete; no browser HTTP client or concurrent stream certification'

def sql_workflow(cfg):
    details=event_lifecycle(lambda tenant:MatrixOneAGUIJournal(cfg,tenant))
    import pymysql
    journal=MatrixOneAGUIJournal(cfg,'rollback')
    event=core.RunStartedEvent(thread_id='rollback_thread',run_id='rollback_run')
    journal.append_batch('rollback_run',[event]);before=journal.replay('rollback_run')
    with pymysql.connect(**cfg) as connection:
        connection.begin()
        try:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO ag_ui_journal(tenant,run_id,payload) VALUES(%s,%s,%s)',('rollback','rollback_run',event.model_dump_json(by_alias=True)))
                try:cursor.execute('INSERT INTO ag_ui_journal(tenant,run_id,payload) VALUES(%s,%s,%s)',('rollback','rollback_run','{"broken":'))
                except pymysql.MySQLError:pass
                else:raise AssertionError('SQL accepted invalid JSON')
        finally:connection.rollback()
    assert journal.replay('rollback_run')==before,'Partial transaction survived explicit rollback'
    journal.delete('rollback_run')
    return details+'; valid append followed by SQL-invalid JSON rolls back and preserves pre-existing event'

