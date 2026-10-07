import hashlib
import io
from pathlib import Path
from docx import Document as WordDocument
from pypdf import PdfReader
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI
from claimiq.config import get_settings

class RAGService:
    def __init__(self):
        s = get_settings(); self.s = s
        required = [s.azure_openai_endpoint, s.azure_openai_api_key, s.azure_openai_chat_deployment, s.azure_openai_embedding_deployment, s.azure_search_endpoint, s.azure_search_key]
        if not all(required): raise RuntimeError("Azure OpenAI and Azure AI Search settings are required")
        self.openai = AzureOpenAI(azure_endpoint=s.azure_openai_endpoint, api_key=s.azure_openai_api_key, api_version=s.azure_openai_api_version)
        self.search = SearchClient(s.azure_search_endpoint, s.azure_search_index, AzureKeyCredential(s.azure_search_key))

    def extract(self, data: bytes, name: str):
        low = name.lower()
        if low.endswith(".pdf"):
            return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(io.BytesIO(data)).pages)]
        if low.endswith(".docx"):
            doc = WordDocument(io.BytesIO(data)); return [(1, "\n".join(paragraph.text for paragraph in doc.paragraphs))]
        if low.endswith(".txt"):
            return [(1, data.decode("utf-8"))]
        raise ValueError("Only PDF, DOCX and TXT are supported")

    def embedding(self, text: str):
        return self.openai.embeddings.create(model=self.s.azure_openai_embedding_deployment, input=text).data[0].embedding

    def ingest(self, data: bytes, document_id: str, name: str) -> int:
        rows = []
        for page, raw in self.extract(data, name):
            text = " ".join(raw.split())
            for number, start in enumerate(range(0, len(text), 1020)):
                chunk = text[start:start + 1200]
                if not chunk: continue
                rows.append({"id": hashlib.sha256(f"{document_id}-{page}-{number}".encode()).hexdigest(), "document_id": document_id, "document_name": name, "section": f"page-{page}", "page": page, "content": chunk, "content_vector": self.embedding(chunk), "active": True})
        if rows: self.search.upload_documents(rows)
        return len(rows)

    def set_active(self, document_id: str, active: bool):
        found = list(self.search.search("*", filter=f"document_id eq '{document_id}'", select=["id"]))
        if found: self.search.merge_documents([{"id": x["id"], "active": active} for x in found])

    def ask(self, question: str):
        vector = VectorizedQuery(vector=self.embedding(question), k_nearest_neighbors=self.s.rag_top_k, fields="content_vector")
        found = list(self.search.search(search_text=question, vector_queries=[vector], filter="active eq true", select=["content", "document_name", "section", "page"], top=self.s.rag_top_k))
        found = [x for x in found if float(x.get("@search.score", 0)) >= self.s.rag_min_score]
        if not found:
            return {"answer": "No relevant information was found in the approved documents.", "sources": [], "low_confidence": True, "prompt_tokens": 0, "completion_tokens": 0}
        context = "\n\n".join(
            f"[S{n}] {item['document_name']} | {item.get('section', '')} | page {item.get('page', '?')}\n{item['content']}"
            for n, item in enumerate(found, 1)
        )[:self.s.rag_max_context_chars]
        system = (
            "Answer only from SOURCES. Cite factual statements using [S#]. "
            "Never fabricate clauses, numbers or amounts. If the sources do not answer the question, say: "
            "No relevant information was found in the approved documents.\nSOURCES:\n" + context
        )
        #response = self.openai.chat.completions.create(model=self.s.azure_openai_chat_deployment, temperature=0, max_tokens=500, messages=[{"role":"system","content":system},{"role":"user","content":question}])
        response = self.openai.chat.completions.create(
            model=self.s.azure_openai_chat_deployment,
            max_completion_tokens=500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question}
            ]
        )
        usage = response.usage
        return {"answer": response.choices[0].message.content, "sources": [{"document":x["document_name"], "section":x.get("section"), "page":x.get("page")} for x in found], "low_confidence": False, "prompt_tokens": usage.prompt_tokens if usage else 0, "completion_tokens": usage.completion_tokens if usage else 0}

def save_document(data: bytes, original_name: str) -> str:
    root = Path(get_settings().document_dir); root.mkdir(parents=True, exist_ok=True)
    filename = f"{hashlib.sha256(data).hexdigest()}-{Path(original_name).name}"
    path = root / filename; path.write_bytes(data); return str(path)
