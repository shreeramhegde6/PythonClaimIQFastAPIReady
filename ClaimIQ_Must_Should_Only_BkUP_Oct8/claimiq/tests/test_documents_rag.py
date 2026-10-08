from claimiq import routes

class FakeRAG:
    active_calls=[]
    def ingest(self, data, document_id, name):
        assert data
        return 3
    def set_active(self, document_id, active):
        self.active_calls.append((document_id,active))
    def ask(self, question):
        return {
            "answer":"Grounded test answer [S1]",
            "sources":[{"document":"policy.txt","section":"page-1","page":1}],
            "low_confidence":False,"prompt_tokens":10,"completion_tokens":5
        }

class NoMatchRAG(FakeRAG):
    def ask(self, question):
        return {"answer":"No relevant information was found in the approved documents.","sources":[],"low_confidence":True,"prompt_tokens":0,"completion_tokens":0}

class BrokenRAG(FakeRAG):
    def ingest(self, data, document_id, name):
        raise RuntimeError("simulated embedding failure")

def patch_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(routes, "save_document", lambda data, name: str(tmp_path / name))

def test_admin_uploads_txt_document(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(routes,"RAGService",FakeRAG); patch_storage(monkeypatch,tmp_path)
    response=client.post("/api/v1/documents",headers=admin_headers,files={"file":("policy.txt",b"Approved policy text","text/plain")})
    assert response.status_code == 201, response.text
    assert response.json()["chunks"] == 3
    assert response.json()["active"] is True

def test_non_admin_cannot_upload_document(client, support_headers):
    response=client.post("/api/v1/documents",headers=support_headers,files={"file":("policy.txt",b"text","text/plain")})
    assert response.status_code == 403

def test_unsupported_document_type_rejected(client, admin_headers):
    response=client.post("/api/v1/documents",headers=admin_headers,files={"file":("policy.csv",b"a,b","text/csv")})
    assert response.status_code == 415

def test_duplicate_document_rejected(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(routes,"RAGService",FakeRAG); patch_storage(monkeypatch,tmp_path)
    files={"file":("policy.txt",b"same content","text/plain")}
    assert client.post("/api/v1/documents",headers=admin_headers,files=files).status_code == 201
    files={"file":("policy.txt",b"same content","text/plain")}
    response=client.post("/api/v1/documents",headers=admin_headers,files=files)
    assert response.status_code == 409

def test_ingestion_failure_returns_503(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(routes,"RAGService",BrokenRAG); patch_storage(monkeypatch,tmp_path)
    response=client.post("/api/v1/documents",headers=admin_headers,files={"file":("policy.txt",b"text","text/plain")})
    assert response.status_code == 503

def test_list_documents(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(routes,"RAGService",FakeRAG); patch_storage(monkeypatch,tmp_path)
    client.post("/api/v1/documents",headers=admin_headers,files={"file":("policy.txt",b"text","text/plain")})
    response=client.get("/api/v1/documents",headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_deactivate_document(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(routes,"RAGService",FakeRAG); patch_storage(monkeypatch,tmp_path)
    created=client.post("/api/v1/documents",headers=admin_headers,files={"file":("policy.txt",b"text","text/plain")}).json()
    response=client.patch(f"/api/v1/documents/{created['id']}/active",headers=admin_headers,params={"active":False})
    assert response.status_code == 200
    assert response.json()["active"] is False

def test_ai_query_returns_citation(client, admin_headers, monkeypatch):
    monkeypatch.setattr(routes,"RAGService",FakeRAG)
    response=client.post("/api/v1/ai/query",headers=admin_headers,json={"question":"What is covered?"})
    assert response.status_code == 200, response.text
    body=response.json()
    assert body["sources"][0]["document"] == "policy.txt"
    assert "[S1]" in body["answer"]

def test_ai_query_no_match(client, admin_headers, monkeypatch):
    monkeypatch.setattr(routes,"RAGService",NoMatchRAG)
    response=client.post("/api/v1/ai/query",headers=admin_headers,json={"question":"Unrelated question"})
    assert response.status_code == 200
    assert response.json()["low_confidence"] is True
    assert response.json()["sources"] == []

def test_ai_question_validation(client, admin_headers):
    response=client.post("/api/v1/ai/query",headers=admin_headers,json={"question":"x"})
    assert response.status_code == 422
