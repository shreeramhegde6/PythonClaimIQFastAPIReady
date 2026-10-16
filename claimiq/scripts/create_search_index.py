import json
import os
from pathlib import Path
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndex
endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
key = os.environ["AZURE_SEARCH_KEY"]
schema = json.loads(Path("infra/search-index.json").read_text())
SearchIndexClient(endpoint, AzureKeyCredential(key)).create_or_update_index(SearchIndex.deserialize(schema))
print("Search index ready")
