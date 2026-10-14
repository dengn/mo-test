"""LangExtract document roundtrip through its public JSON conversion helpers."""
from langextract import data_lib
from langextract.core.data import AnnotatedDocument

class LangExtractDocumentStore:
    def __init__(self,snapshots):self.snapshots=snapshots
    def save(self,key,document):
        if not isinstance(document,AnnotatedDocument):raise TypeError('AnnotatedDocument is required')
        self.snapshots.save(key,data_lib.annotated_document_to_dict(document))
    def load(self,key):
        value=self.snapshots.load(key)
        return data_lib.dict_to_annotated_document(value) if value is not None else None
    def delete(self,key):self.snapshots.delete(key)
