import pytest
from adapters.camel_storage import MatrixOneCamelStorage
from flows.camel_workflow import lifecycle

@pytest.mark.project('camel')
def test_camel_chat_agent_history_restore_continue(db):
    lifecycle(lambda namespace:MatrixOneCamelStorage(db.config,namespace))
    store=MatrixOneCamelStorage(db.config,'atomic');store.save([{'valid':1}]);before=store.load()
    for batch in [[{'valid':2},{'invalid':object()}],[{'valid':2},{'invalid':float('nan')}],[{'valid':2},3]]:
        with pytest.raises((TypeError,ValueError)):store.save(batch)
        assert store.load()==before

@pytest.mark.project('camel')
def test_camel_native_json_reference(tmp_path):
    import uuid
    from camel.storages.key_value_storages import JsonStorage
    paths={}
    def factory(namespace):
        paths.setdefault(namespace,tmp_path/(uuid.uuid4().hex+'.jsonl'))
        return JsonStorage(paths[namespace])
    lifecycle(factory)
