import json,copy,hashlib
from pathlib import Path
import langextract as lx
from langextract import data_lib
from langextract.core.base_model import BaseLanguageModel
from langextract.core.types import ScoredOutput
from langextract.resolver import ResolverParsingError
from adapters.framework_json import MatrixOneJsonSnapshots
from adapters.langextract_store import LangExtractDocumentStore

class FixtureExtractor(BaseLanguageModel):

    def __init__(self, output):
        super().__init__()
        self.output = output
        self.prompts = []

    def infer(self, batch_prompts, **kwargs):
        for prompt in batch_prompts:
            self.prompts.append(prompt)
            yield [ScoredOutput(score=1.0, output=self.output)]

class NativeJsonlDocuments:

    def __init__(self, directory, namespace):
        self.directory = Path(directory)
        self.namespace = namespace

    def _path(self, key):
        return self.directory / (hashlib.sha256((self.namespace + '\x00' + key).encode()).hexdigest() + '.jsonl')

    def save(self, key, document):
        path = self._path(key)
        lx.io.save_annotated_documents(iter([document]), output_dir=self.directory, output_name=path.name, show_progress=False)

    def load(self, key):
        path = self._path(key)
        return next(lx.io.load_annotated_documents_jsonl(path)) if path.exists() else None

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

def extraction_lifecycle(factory):
    text = 'Alice met Bob in 北京.'
    examples = [lx.data.ExampleData(text='Carol in 上海.', extractions=[lx.data.Extraction(extraction_class='person', extraction_text='Carol'), lx.data.Extraction(extraction_class='location', extraction_text='上海')])]
    output = json.dumps({'extractions': [{'person': 'Alice', 'person_attributes': {'role': 'visitor'}}, {'person': 'Bob', 'person_attributes': {'role': 'host'}}, {'location': '北京', 'location_attributes': {'country': 'CN'}}]}, ensure_ascii=False)
    model = FixtureExtractor(output)
    result = lx.extract(text_or_documents=text, prompt_description='Extract people and location verbatim.', examples=examples, model=model, use_schema_constraints=False, fence_output=False, max_workers=1, show_progress=False, resolver_params={'suppress_parse_errors': False})
    assert result.text == text and len(result.extractions) == 3, result
    assert model.prompts and text in model.prompts[-1]
    assert [e.extraction_text for e in result.extractions] == ['Alice', 'Bob', '北京']
    for extraction in result.extractions:
        interval = extraction.char_interval
        assert interval is not None
        assert text[interval.start_pos:interval.end_pos] == extraction.extraction_text
    original = data_lib.annotated_document_to_dict(result)
    store = factory('a')
    store.save('doc', result)
    restored = factory('a').load('doc')
    assert data_lib.annotated_document_to_dict(restored) == original
    assert isinstance(restored, lx.data.AnnotatedDocument)
    other = copy.deepcopy(result)
    other.extractions[0].attributes = {'role': 'tenant_b', 'verified': True}
    factory('b').save('doc', other)
    assert factory('a').load('doc').extractions[0].attributes == {'role': 'visitor'}
    assert factory('b').load('doc').extractions[0].attributes['verified'] is True
    assert factory("a' OR 1=1 --").load('doc') is None
    updated = copy.deepcopy(result)
    updated.extractions[0].attributes = {'role': 'updated', 'version': 2}
    store.save('doc', updated)
    assert factory('a').load('doc').extractions[0].attributes == {'role': 'updated', 'version': 2}
    before = data_lib.annotated_document_to_dict(factory('a').load('doc'))
    try:
        lx.extract(text_or_documents=text, prompt_description='Extract people.', examples=examples, model=FixtureExtractor('not valid JSON'), use_schema_constraints=False, fence_output=False, show_progress=False, resolver_params={'suppress_parse_errors': False})
    except ResolverParsingError:
        pass
    else:
        raise AssertionError('Invalid provider output was silently accepted')
    assert data_lib.annotated_document_to_dict(factory('a').load('doc')) == before
    store.delete('doc')
    assert factory('a').load('doc') is None
    assert factory('b').load('doc') is not None
    return 'native lx.extract/provider infer/parser/character alignment; typed AnnotatedDocument converted by public helpers, reopen/Unicode/attributes/upsert/tenant/delete; native JSONL reference; malformed provider output explicitly rejected; fixed provider, no extraction-quality or real-model certification'

def sql_workflow(cfg):
    return extraction_lifecycle(lambda tenant: LangExtractDocumentStore(MatrixOneJsonSnapshots(cfg, tenant)))
