# Ví dụ cụ thể: Toàn bộ luồng Search Mix của LightRAG

Câu hỏi: **"Điều kiện thành lập doanh nghiệp tư nhân là gì?"**

Tôi sẽ trace từng bước, cho thấy **dữ liệu thực sự trông như thế nào** tại mỗi giai đoạn.

---

## Bước 1: User gửi query

```python
await rag_orchestrator.query(
    message="Điều kiện thành lập doanh nghiệp tư nhân là gì?",
    mode="mix",
    stream=False
)
```

---

## Bước 2: LLM trích xuất keywords

LightRAG gửi cho LLM prompt:

```
Bạn là chuyên gia trích xuất keywords cho hệ thống RAG.
Trích xuất high_level_keywords và low_level_keywords từ query sau:
Query: "Điều kiện thành lập doanh nghiệp tư nhân là gì?"
```

LLM trả về:

```json
{
    "high_level_keywords": ["Điều kiện thành lập doanh nghiệp", "Quy định pháp luật doanh nghiệp"],
    "low_level_keywords": ["Doanh nghiệp tư nhân", "Luật Doanh Nghiệp", "Giấy phép kinh doanh"]
}
```

Sau bước này:
- `hl_keywords` = `"Điều kiện thành lập doanh nghiệp, Quy định pháp luật doanh nghiệp"`
- `ll_keywords` = `"Doanh nghiệp tư nhân, Luật Doanh Nghiệp, Giấy phép kinh doanh"`

---

## Bước 3: Batch embed 3 texts cùng lúc

```python
texts_to_embed = [
    "Điều kiện thành lập doanh nghiệp tư nhân là gì?",   # query gốc
    "Doanh nghiệp tư nhân, Luật Doanh Nghiệp, Giấy phép kinh doanh",  # ll_keywords
    "Điều kiện thành lập doanh nghiệp, Quy định pháp luật doanh nghiệp",  # hl_keywords
]
# → 1 API call duy nhất → 3 embeddings vectors (768 chiều mỗi vector)
```

Kết quả: `query_embedding`, `ll_embedding`, `hl_embedding` — 3 vectors số thực.

---

## Bước 4: Song song 3 nguồn search

### 4A. Entity Vector Search (`ll_keywords` → `entities_vdb`)

```python
results = await entities_vdb.query("Doanh nghiệp tư nhân, Luật Doanh Nghiệp, ...", top_k=10)
```

Milvus/Zilliz tìm cosine similarity → trả về danh sách entities gần nhất:

```
entities_vdb trả về:
┌──────────────────────────────┬────────────┐
│ entity_name                  │ similarity │
├──────────────────────────────┼────────────┤
│ Doanh Nghiệp Tư Nhân        │ 0.94       │
│ Luật Doanh Nghiệp 2020      │ 0.89       │
│ Giấy Chứng Nhận Đăng Ký     │ 0.82       │
│ Sở Kế Hoạch Đầu Tư          │ 0.78       │
│ Vốn Điều Lệ                 │ 0.75       │
└──────────────────────────────┴────────────┘
```

Tiếp theo, LightRAG lấy **data đầy đủ** từ **Neo4j** cho 5 entities này:

```python
nodes_dict = await knowledge_graph_inst.get_nodes_batch(
    ["Doanh Nghiệp Tư Nhân", "Luật Doanh Nghiệp 2020", ...]
)
```

Neo4j trả về:

```
Doanh Nghiệp Tư Nhân:
  - entity_type: "LEGAL_ENTITY"
  - description: "Doanh nghiệp do một cá nhân làm chủ..."
  - source_id: "chunk-001<GRAPH_FIELD_SEP>chunk-002"   ← chunks chứa entity này

Luật Doanh Nghiệp 2020:
  - entity_type: "LEGAL_DOCUMENT"
  - description: "Văn bản quy phạm pháp luật..."
  - source_id: "chunk-001<GRAPH_FIELD_SEP>chunk-003"
```

Rồi tìm **tất cả edges** nối với 5 entities → **local_relations**:

```python
edges = await knowledge_graph_inst.get_nodes_edges_batch(
    ["Doanh Nghiệp Tư Nhân", "Luật Doanh Nghiệp 2020", ...]
)
```

```
Neo4j trả về các edges:
  (Doanh Nghiệp Tư Nhân) ──được quy định bởi──→ (Luật Doanh Nghiệp 2020)
  (Doanh Nghiệp Tư Nhân) ──đăng ký tại──→ (Sở Kế Hoạch Đầu Tư)
  (Doanh Nghiệp Tư Nhân) ──yêu cầu──→ (Vốn Điều Lệ)
  (Luật Doanh Nghiệp 2020) ──ban hành bởi──→ (Quốc Hội)
```

**Kết quả 4A**: `local_entities` (5 entities) + `local_relations` (4 relations)

---

### 4B. Relationship Vector Search (`hl_keywords` → `relationships_vdb`)

```python
results = await relationships_vdb.query("Điều kiện thành lập doanh nghiệp, ...", top_k=10)
```

Milvus tìm relationships có description/keywords gần nhất:

```
relationships_vdb trả về:
┌─────────────────────────┬──────────────────────┬────────────┐
│ src_id                  │ tgt_id               │ similarity │
├─────────────────────────┼──────────────────────┼────────────┤
│ Doanh Nghiệp            │ Luật Doanh Nghiệp    │ 0.91       │
│ Điều Kiện Thành Lập     │ Doanh Nghiệp Tư Nhân │ 0.88       │
│ Chủ Sở Hữu             │ Doanh Nghiệp Tư Nhân │ 0.80       │
└─────────────────────────┴──────────────────────┘
```

Rồi tìm ngược lại: entities nào nối với relationships này → **global_entities**:

```
global_entities: [Doanh Nghiệp, Luật Doanh Nghiệp, Điều Kiện Thành Lập, 
                  Doanh Nghiệp Tư Nhân, Chủ Sở Hữu]
```

**Kết quả 4B**: `global_relations` (3 relations) + `global_entities` (5 entities)

---

### 4C. Document Chunks Vector Search (chỉ trong mode `mix`)

```python
results = await chunks_vdb.query("Điều kiện thành lập doanh nghiệp tư nhân là gì?", top_k=20)
```

Milvus tìm chunks có nội dung gần nhất với query:

```
chunks_vdb trả về:
┌────────────┬──────────────────────────────────────────────────────┬────────────┐
│ chunk_id   │ content (preview)                                    │ similarity │
├────────────┼──────────────────────────────────────────────────────┼────────────┤
│ chunk-001  │ "Điều 188. Doanh nghiệp tư nhân. 1. DNTN là DN..." │ 0.93       │
│ chunk-002  │ "Điều 189. Vốn đầu tư của chủ DNTN. Vốn đầu..."   │ 0.87       │
│ chunk-010  │ "Điều 17. Quyền thành lập DN. Tổ chức, cá nhân..." │ 0.84       │
│ chunk-015  │ "Điều 27. Hồ sơ đăng ký DNTN. 1. Giấy đề nghị..." │ 0.79       │
└────────────┴──────────────────────────────────────────────────────┴────────────┘
```

**Kết quả 4C**: `vector_chunks` (4 chunks với nội dung text)

---

## Bước 5: Round-robin merge

```
local_entities:  [DN Tư Nhân,    Luật DN 2020,   Giấy CN,        Sở KHĐT,        Vốn ĐL]
global_entities: [Doanh Nghiệp,  Luật DN,        Điều Kiện TL,   DN Tư Nhân,     Chủ Sở Hữu]
                      ↓               ↓               ↓               ↓               ↓
final_entities:  [DN Tư Nhân,    Doanh Nghiệp,   Luật DN 2020,   Luật DN,        Giấy CN, 
                  Điều Kiện TL,  Sở KHĐT,        DN Tư Nhân(dup), Vốn ĐL,       Chủ Sở Hữu]
                                                  ↑ bỏ trùng
```

Kết quả sau dedup: **8 entities**, **~6 relations** (tương tự)

---

## Bước 6: Token truncation

```
max_entity_tokens = 4000
max_relation_tokens = 4000

Entities (8 cái) → format JSON → đếm tokens → 2800 tokens < 4000 → GIỮ HẾT ✅
Relations (6 cái) → format JSON → đếm tokens → 1500 tokens < 4000 → GIỮ HẾT ✅
```

Nếu quá nhiều entities/relations mà vượt token budget → cắt bớt từ cuối.

---

## Bước 7: Merge chunks từ 3 nguồn

Chunks lấy từ:
- **Entity source_id** (E): chunks mà entities được trích xuất từ đó → chunk-001, chunk-002, chunk-003
- **Relation source_id** (R): chunks mà relations được trích xuất từ đó → chunk-001, chunk-003
- **Vector search** (C): chunks tìm trực tiếp → chunk-001, chunk-002, chunk-010, chunk-015

```
Sau dedup:
┌────────────┬────────┬──────────────────────────────────────────────┐
│ chunk_id   │ source │ content                                      │
├────────────┼────────┼──────────────────────────────────────────────┤
│ chunk-001  │ E+R+C  │ "Điều 188. Doanh nghiệp tư nhân. 1. DNTN..." │
│ chunk-002  │ E+C    │ "Điều 189. Vốn đầu tư của chủ DNTN..."      │
│ chunk-003  │ E+R    │ "Điều 190. Quản lý doanh nghiệp tư nhân..." │
│ chunk-010  │ C      │ "Điều 17. Quyền thành lập DN..."             │
│ chunk-015  │ C      │ "Điều 27. Hồ sơ đăng ký DNTN..."            │
└────────────┴────────┴──────────────────────────────────────────────┘
```

> chunk-001 xuất hiện trong cả 3 nguồn → rất relevant!

---

## Bước 8: Tách thành 2 FORMAT khác nhau

> [!IMPORTANT]
> Đây là điểm mấu chốt bạn hỏi: **cùng 1 dữ liệu**, nhưng format khác nhau cho 2 mục đích.

### FORMAT A — Context string gửi cho LLM

Dữ liệu trên được **format thành 1 chuỗi text dài**, nhét vào system prompt:

```
--- system prompt ---

You are an expert AI assistant...
Generate a comprehensive answer using the Context below.

---Context---

Knowledge Graph Data (Entity):

```json
{"entity": "Doanh Nghiệp Tư Nhân", "type": "LEGAL_ENTITY", "description": "Doanh nghiệp do một cá nhân làm chủ và tự chịu trách nhiệm bằng toàn bộ tài sản", "file_path": "luat_dn_2020.md"}
{"entity": "Luật Doanh Nghiệp 2020", "type": "LEGAL_DOCUMENT", "description": "Văn bản quy phạm pháp luật quy định về thành lập, tổ chức quản lý, tổ chức lại, giải thể doanh nghiệp", "file_path": "luat_dn_2020.md"}
{"entity": "Vốn Điều Lệ", "type": "CONCEPT", "description": "Tổng giá trị tài sản do các thành viên đóng góp hoặc cam kết góp khi thành lập", "file_path": "luat_dn_2020.md"}
```

Knowledge Graph Data (Relationship):

```json
{"entity1": "Doanh Nghiệp Tư Nhân", "entity2": "Luật Doanh Nghiệp 2020", "description": "được quy định tại Chương VII", "keywords": "quy định pháp luật"}
{"entity1": "Doanh Nghiệp Tư Nhân", "entity2": "Sở Kế Hoạch Đầu Tư", "description": "phải đăng ký kinh doanh tại", "keywords": "đăng ký"}
```

Document Chunks:

```json
{"reference_id": "1", "content": "Điều 188. Doanh nghiệp tư nhân\n1. Doanh nghiệp tư nhân là doanh nghiệp do một cá nhân làm chủ và tự chịu trách nhiệm bằng toàn bộ tài sản của mình về mọi hoạt động của doanh nghiệp.\n2. Doanh nghiệp tư nhân không được phát hành bất kỳ loại chứng khoán nào.\n3. Mỗi cá nhân chỉ được quyền thành lập một doanh nghiệp tư nhân. Chủ doanh nghiệp tư nhân không được đồng thời là chủ hộ kinh doanh, thành viên hợp danh của công ty hợp danh."}
{"reference_id": "1", "content": "Điều 189. Vốn đầu tư của chủ doanh nghiệp tư nhân\n1. Vốn đầu tư của chủ doanh nghiệp tư nhân do chủ doanh nghiệp tư nhân tự đăng ký. Chủ DNTN có nghĩa vụ đăng ký chính xác tổng số vốn đầu tư."}
{"reference_id": "2", "content": "Điều 27. Hồ sơ đăng ký doanh nghiệp tư nhân\n1. Giấy đề nghị đăng ký doanh nghiệp.\n2. Bản sao giấy tờ pháp lý của cá nhân đối với chủ doanh nghiệp tư nhân."}
```

Reference Document List:

[1] luat_dn_2020.md
[2] nghi_dinh_01_2021.md
```

Rồi LLM nhận: `system_prompt` (chứa context ở trên) + `user_query` ("Điều kiện thành lập doanh nghiệp tư nhân là gì?")

LLM sinh ra câu trả lời:

```
Theo Luật Doanh Nghiệp 2020, điều kiện thành lập doanh nghiệp tư nhân bao gồm:

1. **Chủ sở hữu phải là cá nhân** — DNTN là doanh nghiệp do một cá nhân làm chủ...
2. **Chỉ được thành lập 1 DNTN** — Mỗi cá nhân chỉ được quyền thành lập một DNTN...
3. **Không được đồng thời là chủ hộ kinh doanh**...

### References
- [1] luat_dn_2020.md
- [2] nghi_dinh_01_2021.md
```

### FORMAT B — Data dict trả về cho API

**Cùng dữ liệu**, nhưng format thành Python dict:

```python
{
    "status": "success",
    "data": {
        "entities": [
            {"entity_name": "Doanh Nghiệp Tư Nhân", "entity_type": "LEGAL_ENTITY", 
             "description": "Doanh nghiệp do một cá nhân làm chủ...", 
             "source_id": "chunk-001<sep>chunk-002", "file_path": "luat_dn_2020.md"},
            {"entity_name": "Luật Doanh Nghiệp 2020", ...},
            {"entity_name": "Vốn Điều Lệ", ...},
            ...
        ],
        "relationships": [
            {"src_id": "Doanh Nghiệp Tư Nhân", "tgt_id": "Luật Doanh Nghiệp 2020",
             "description": "được quy định tại Chương VII", ...},
            ...
        ],
        "chunks": [
            {"reference_id": "1", "chunk_id": "chunk-001",
             "content": "Điều 188. Doanh nghiệp tư nhân\n1. Doanh nghiệp tư nhân là...",
             "file_path": "luat_dn_2020.md"},
            {"reference_id": "1", "chunk_id": "chunk-002",
             "content": "Điều 189. Vốn đầu tư của chủ doanh nghiệp tư nhân...",
             "file_path": "luat_dn_2020.md"},
            {"reference_id": "2", "chunk_id": "chunk-015",
             "content": "Điều 27. Hồ sơ đăng ký doanh nghiệp tư nhân...",
             "file_path": "nghi_dinh_01_2021.md"},
        ],
        "references": [
            {"reference_id": "1", "file_path": "luat_dn_2020.md"},
            {"reference_id": "2", "file_path": "nghi_dinh_01_2021.md"},
        ]
    },
    "metadata": {
        "query_mode": "mix",
        "keywords": {
            "high_level": ["Điều kiện thành lập doanh nghiệp", "Quy định pháp luật"],
            "low_level": ["Doanh nghiệp tư nhân", "Luật Doanh Nghiệp"]
        }
    },
    "llm_response": {
        "content": "Theo Luật Doanh Nghiệp 2020, điều kiện thành lập...",
        "is_streaming": false
    }
}
```

---

## Tổng kết: 2 FORMAT từ cùng 1 dữ liệu

```
Bước 1-7: Search → merge → truncate
              │
              │ ra được: 8 entities + 6 relations + 5 chunks
              │
              ├────────────────────────────────────────┐
              │                                        │
              ▼                                        ▼
     FORMAT A: Text string                    FORMAT B: Python dict
     ┌─────────────────────┐                  ┌───────────────────────┐
     │ KG Entity:          │                  │ "data": {             │
     │ {"entity": "DN..."} │                  │   "entities": [...],  │
     │                     │                  │   "relationships":[], │
     │ KG Relationship:    │                  │   "chunks": [         │
     │ {"entity1": "DN.."} │                  │     {"content":"..."},│
     │                     │                  │   ],                  │
     │ Document Chunks:    │                  │   "references": [...] │
     │ {"content": "Đ188"} │                  │ }                     │
     │                     │                  │ "llm_response": {     │
     │ Reference List:     │                  │   "content": "Theo.." │
     │ [1] luat_dn.md      │                  │ }                     │
     └────────┬────────────┘                  └───────────┬───────────┘
              │                                           │
              ▼                                           ▼
     Nhét vào system_prompt                      Trả về cho:
     → Gửi cho LLM                               - API endpoint
     → LLM sinh answer                           - Frontend hiển thị
                                                  - RAGAS evaluation
```

> [!NOTE]
> **FORMAT A** (text) chứa cùng nội dung với **FORMAT B** (dict), chỉ khác cách trình bày.
> LLM đọc text, còn code/API đọc dict.
> Khi evaluation lấy `data.chunks[].content` — đó chính là **cùng nội dung** mà LLM đã đọc trong context string.
