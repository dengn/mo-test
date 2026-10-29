import uuid
from pydantic import BaseModel,Field
from crewai.flow.flow import Flow,start,listen
from crewai.flow.persistence import persist

class State(BaseModel):
    counter: int = 0
    notes: list[str] = Field(default_factory=list)

def flow_class(store):

    @persist(persistence=store)
    class CounterFlow(Flow[State]):

        @start()
        def count(self):
            self.state.counter += 1
            self.state.notes.append('中文')
            return self.state.counter

        @listen(count)
        def finish(self, value):
            self.state.counter += 10
            return self.state.counter
    return CounterFlow

def lifecycle(store, new_store):
    cls = flow_class(store)
    first = cls(tracing=False)
    assert first.kickoff() == 11
    id = str(first.state.id)
    assert store.load_state(id)['counter'] == 11
    reopened = new_store()
    restored = flow_class(reopened)(tracing=False)
    assert restored.kickoff(inputs={'id': id}) == 22
    assert restored.state.notes == ['中文', '中文']
    assert reopened.load_state(id)['counter'] == 22
    other = flow_class(reopened)(tracing=False)
    assert other.kickoff() == 11
    assert reopened.load_state(str(other.state.id))['counter'] == 11
    assert reopened.load_state(id)['counter'] == 22
    assert reopened.load_state(str(uuid.uuid4())) is None
    assert reopened.load_state("x' OR 1=1 --") is None
    latest_id = str(uuid.uuid4())
    reopened.save_state(latest_id, 'step_one', {'id': latest_id, 'counter': 1})
    reopened.save_state(latest_id, 'step_two', {'id': latest_id, 'counter': 2, 'notes': ['中文']})
    assert reopened.load_state(latest_id) == {'id': latest_id, 'counter': 2, 'notes': ['中文']}
    try:
        reopened.save_state(latest_id, 'bad', 3)
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError('Invalid state silently accepted')
    return 'native @persist Flow.kickoff/start/listen; typed state saved/restored and continued 11→22; append order, separate flows, Unicode, missing/injection-like id; no LLM, async feedback/concurrency not tested'
