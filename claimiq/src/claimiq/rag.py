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
        s = get_settings()
        self.s = s

        required = [
            s.azure_openai_endpoint,
            s.azure_openai_api_key,
            s.azure_openai_chat_deployment,
            s.azure_openai_embedding_deployment,
            s.azure_search_endpoint,
            s.azure_search_key,
        ]

        if not all(required):
            raise RuntimeError(
                "Azure OpenAI and Azure AI Search settings are required"
            )

        self.openai = AzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
        )

        self.search = SearchClient(
            endpoint=s.azure_search_endpoint,
            index_name=s.azure_search_index,
            credential=AzureKeyCredential(s.azure_search_key),
        )

    def extract(self, data: bytes, name: str):
        low = name.lower()

        if low.endswith(".pdf"):
            return [
                (i + 1, page.extract_text() or "")
                for i, page in enumerate(
                    PdfReader(io.BytesIO(data)).pages
                )
            ]

        if low.endswith(".docx"):
            doc = WordDocument(io.BytesIO(data))

            text = "\n".join(
                paragraph.text
                for paragraph in doc.paragraphs
            )

            return [(1, text)]

        if low.endswith(".txt"):
            return [(1, data.decode("utf-8"))]

        raise ValueError(
            "Only PDF, DOCX and TXT are supported"
        )

    def embedding(self, text: str):
        response = self.openai.embeddings.create(
            model=self.s.azure_openai_embedding_deployment,
            input=text,
        )

        return response.data[0].embedding

    def ingest(
        self,
        data: bytes,
        document_id: str,
        name: str,
    ) -> int:

        rows = []

        for page, raw in self.extract(data, name):

            text = " ".join(raw.split())

            for number, start in enumerate(
                range(0, len(text), 1020)
            ):

                chunk = text[start:start + 1200]

                if not chunk:
                    continue

                rows.append(
                    {
                        "id": hashlib.sha256(
                            f"{document_id}-{page}-{number}".encode()
                        ).hexdigest(),

                        "document_id": document_id,
                        "document_name": name,
                        "section": f"page-{page}",
                        "page": page,
                        "content": chunk,

                        "content_vector": self.embedding(chunk),

                        "active": True,
                    }
                )

        if rows:
            result = self.search.upload_documents(rows)

            failed = [
                item
                for item in result
                if not item.succeeded
            ]

            if failed:
                raise RuntimeError(
                    f"Azure AI Search failed to upload "
                    f"{len(failed)} chunk(s)"
                )

        return len(rows)

    def set_active(
        self,
        document_id: str,
        active: bool,
    ):

        found = list(
            self.search.search(
                search_text="*",
                filter=f"document_id eq '{document_id}'",
                select=["id"],
            )
        )

        if found:
            self.search.merge_documents(
                [
                    {
                        "id": item["id"],
                        "active": active,
                    }
                    for item in found
                ]
            )

    def ask(self, question: str):

        # --------------------------------------------------
        # 1. Generate embedding for the user's question
        # --------------------------------------------------

        question_vector = self.embedding(question)

        # --------------------------------------------------
        # 2. Vector query against Azure AI Search
        # --------------------------------------------------

        vector_query = VectorizedQuery(
            vector=question_vector,
            k_nearest_neighbors=self.s.rag_top_k,
            fields="content_vector",
        )

        found = list(
            self.search.search(
                search_text=question,
                vector_queries=[vector_query],
                filter="active eq true",
                select=[
                    "content",
                    "document_name",
                    "section",
                    "page",
                ],
                top=self.s.rag_top_k,
            )
        )

        # --------------------------------------------------
        # 3. Remove low-score results
        # --------------------------------------------------

        found = [
            item
            for item in found
            if float(
                item.get("@search.score", 0)
            ) >= self.s.rag_min_score
        ]

        if not found:
            return {
                "answer": (
                    "No relevant information was found "
                    "in the approved documents."
                ),
                "sources": [],
                "low_confidence": True,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

        # --------------------------------------------------
        # 4. Build context for GPT
        # --------------------------------------------------

        context = "\n\n".join(
            (
                f"[S{n}] "
                f"{item['document_name']} | "
                f"{item.get('section', '')} | "
                f"page {item.get('page', '?')}\n"
                f"{item['content']}"
            )
            for n, item in enumerate(found, 1)
        )

        context = context[
            :self.s.rag_max_context_chars
        ]

        # --------------------------------------------------
        # 5. System prompt
        # --------------------------------------------------

        system = (
            "Answer the user's question using only the SOURCES "
            "provided below. "
            "Cite factual statements using [S#]. "
            "Do not fabricate clauses, numbers, amounts, "
            "coverage, exclusions, or conditions. "
            "If the sources do not contain enough information "
            "to answer the question, respond exactly with: "
            "\"No relevant information was found in the "
            "approved documents.\"\n\n"
            "SOURCES:\n"
            + context
        )

        # --------------------------------------------------
        # 6. Ask GPT-5-mini
        # --------------------------------------------------

        response = self.openai.chat.completions.create(
            model=self.s.azure_openai_chat_deployment,

            # GPT-5-mini:
            # use max_completion_tokens, not max_tokens
            max_completion_tokens=300,

            messages=[
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
        )

        # --------------------------------------------------
        # 7. Debug information
        # --------------------------------------------------

        choice = response.choices[0]

        print(
            "GPT finish_reason:",
            choice.finish_reason,
        )

        print(
            "GPT content:",
            repr(choice.message.content),
        )

        print(
            "GPT usage:",
            response.usage,
        )

        # --------------------------------------------------
        # 8. Protect against blank GPT response
        # --------------------------------------------------

        answer = choice.message.content

        if not answer or not answer.strip():
            answer = (
                "The model returned an empty response. "
                "Please retry the question."
            )

        # --------------------------------------------------
        # 9. Usage
        # --------------------------------------------------

        usage = response.usage

        prompt_tokens = (
            usage.prompt_tokens
            if usage
            else 0
        )

        completion_tokens = (
            usage.completion_tokens
            if usage
            else 0
        )

        # --------------------------------------------------
        # 10. Return API response
        # --------------------------------------------------

        return {
            "answer": answer,

            "sources": [
                {
                    "document": item["document_name"],
                    "section": item.get("section"),
                    "page": item.get("page"),
                }
                for item in found
            ],

            "low_confidence": False,

            "prompt_tokens": prompt_tokens,

            "completion_tokens": completion_tokens,
        }


def save_document(
    data: bytes,
    original_name: str,
) -> str:

    root = Path(
        get_settings().document_dir
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"{hashlib.sha256(data).hexdigest()}-"
        f"{Path(original_name).name}"
    )

    path = root / filename

    path.write_bytes(data)

    return str(path)