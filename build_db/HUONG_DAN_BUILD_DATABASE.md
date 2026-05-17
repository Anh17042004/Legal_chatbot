# 📘 Hướng Dẫn Build Database — LightRAG Legal AI Platform

> **Tác giả:** Auto-generated analysis  
> **Ngày tạo:** 2026-05-14  
> **Phiên bản LightRAG:** lightrag-hku (source fork tại `D:\full_chatbot_lightrag\LightRAG`)

---

## Mục Lục

1. [Tổng Quan Pipeline](#1-tổng-quan-pipeline)
2. [Các Vấn Đề Hiện Tại Trong Neo4j](#2-các-vấn-đề-hiện-tại-trong-neo4j)
3. [Phân Tích Hiệu Năng — Tại Sao Chậm?](#3-phân-tích-hiệu-năng--tại-sao-chậm)
4. [Hướng Dẫn Cấu Hình Đúng](#4-hướng-dẫn-cấu-hình-đúng)
5. [Hướng Dẫn Tối Ưu Tốc Độ](#5-hướng-dẫn-tối-ưu-tốc-độ)
6. [Checklist Trước Khi Chạy](#6-checklist-trước-khi-chạy)

---

## 1. Tổng Quan Pipeline

File `build_database.ipynb` thực hiện pipeline gồm 3 giai đoạn chính:

```
┌─────────────────────────────────────────────────────────────┐
│                    BUILD DATABASE PIPELINE                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  GIAI ĐOẠN 1: Chuẩn Bị Dữ Liệu (Offline - Nhanh)         │
│  ├── Đọc CSV: metadata.csv, relationship.csv, content.csv  │
│  ├── Chunking văn bản pháp luật (SemanticChunker)          │
│  ├── Build entities từ metadata                             │
│  ├── Build relationships từ bảng quan hệ văn bản           │
│  └── Xuất: custom_kg_full.json                             │
│                                                             │
│  GIAI ĐOẠN 2: Nạp Tầng Vĩ Mô — build_macro_layer (Nhanh) │
│  ├── Upsert entities/relations vào VectorDB (Milvus)       │
│  └── Upsert nodes/edges vào GraphDB (Neo4j)                │
│                                                             │
│  GIAI ĐOẠN 3: Nạp Tầng Vi Mô — build_micro_layer (CHẬM)   │
│  ├── Upsert text chunks vào KV Storage                     │
│  ├── Upsert chunk embeddings vào VectorDB (Milvus)         │
│  └── ⚠️ LLM Entity Extraction theo lô BATCH (TỐN NHẤT)    │
│      ├── Gọi LLM extract entities/relations từ mỗi chunk   │
│      └── Merge nodes/edges lên Neo4j + Milvus              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Dữ liệu đầu vào

| File | Mô tả | Số lượng |
|------|--------|----------|
| `metadata.csv` | Thông tin 83 văn bản pháp luật (loại, số hiệu, hiệu lực...) | 83 rows |
| `relationship.csv` | Quan hệ giữa các văn bản (hướng dẫn, thay thế, sửa đổi...) | ~132 rows |
| `content.csv` | Nội dung full-text của 94 văn bản | 94 rows |
| `output_link_sohieu.txt` | Link luatvietnam.vn tương ứng 83 văn bản | 83 rows |

### Databases đích

| Database | Vai trò | Dịch vụ |
|----------|---------|---------|
| **Milvus (Zilliz Cloud)** | Vector DB — lưu embeddings cho entities, relations, chunks | AWS EU-Central |
| **Neo4j (Aura Cloud)** | Graph DB — lưu knowledge graph (nodes + edges) | Neo4j Aura |

---

## 2. Các Vấn Đề Hiện Tại Trong Neo4j

### 2.1 Tất cả Node đều có label `base` — cùng 1 màu

**Triệu chứng:** Mở Neo4j Browser, mọi node đều hiển thị label `base`, cùng 1 màu.

**Nguyên nhân gốc:** LightRAG dùng `workspace` name làm Neo4j label cho **tất cả** nodes. Code xử lý nằm trong `lightrag/kg/neo4j_impl.py`:

```python
# neo4j_impl.py dòng 93-105
def _get_workspace_label(self) -> str:
    workspace = self.workspace.strip()
    if not workspace:
        return "base"       # ← workspace rỗng → label = "base"
    return workspace.replace("`", "``")
```

Câu Cypher tạo node:
```cypher
MERGE (n:`base` {entity_id: $entity_id})
SET n += $properties
```

Trong `build_database.ipynb`, khi khởi tạo LightRAG **không truyền** `workspace`:

```python
rag = LightRAG(
    working_dir=WORKING_DIR,
    # ← THIẾU: workspace="legal_vn"
    ...
)
```

Mặc định (`lightrag.py` dòng 237):
```python
workspace: str = field(default_factory=lambda: os.getenv("WORKSPACE", ""))
```

→ `workspace = ""` → `_get_workspace_label()` trả về `"base"`.

> **⚠️ Lưu ý quan trọng:** Đây là **thiết kế có chủ đích** của LightRAG. Nó sử dụng 1 label duy nhất (workspace name) cho mọi entity node nhằm mục đích **phân tách workspace/tenant**. `entity_type` (concept, person, organization...) chỉ được lưu dưới dạng **property** của node, không phải label. Nếu muốn Neo4j hiển thị nhiều màu theo entity_type, cần dùng Neo4j Bloom hoặc viết script post-processing.

---

### 2.2 Tất cả Relationship chỉ có type `DIRECTED`

**Triệu chứng:** Mọi relationship trong Neo4j đều có type `DIRECTED`, không phân biệt loại quan hệ.

**Nguyên nhân gốc:** Relationship type `DIRECTED` được **hard-coded** trong `neo4j_impl.py`:

```python
# neo4j_impl.py dòng 1175
MERGE (source)-[r:DIRECTED]-(target)
SET r += row.props
```

Thiết kế này áp dụng cho **tất cả** storage backends:

| Backend | Relationship Type |
|---------|------------------|
| Neo4j | `DIRECTED` |
| PostgreSQL/AGE | `DIRECTED` |
| NetworkX | `type="DIRECTED"` |
| Memgraph | `DIRECTED` |

**Ngữ nghĩa thực sự** của mối quan hệ được lưu trong **properties**:
- `keywords`: Từ khóa mô tả loại quan hệ (vd: `"circumstance, division factor"`)
- `description`: Mô tả chi tiết quan hệ

> **⚠️ Không nên** sửa relationship type thành dynamic vì sẽ phá vỡ toàn bộ hệ thống truy vấn Cypher của LightRAG.

---

### 2.3 Description nửa tiếng Anh, nửa tiếng Việt

**Triệu chứng:**
```
"Tài Sản Chung denotes the joint assets of the spouses that are subject to division upon divorce."
```

**Nguyên nhân gốc:** Không set `language` → mặc định = `"English"` (`constants.py` dòng 14):

```python
DEFAULT_SUMMARY_LANGUAGE = "English"
```

Prompt extract entity (`prompt.py` dòng 54):
```
The entire output must be written in `{language}`.
Proper nouns should be retained in their original language...
```

→ LLM viết tiếng Anh nhưng giữ nguyên thuật ngữ pháp lý tiếng Việt → **hỗn hợp 2 ngôn ngữ**.

---

## 3. Phân Tích Hiệu Năng — Tại Sao Chậm?

### 3.1 Sơ đồ thời gian thực tế

```
Chunk 1:  [LLM Extract ~7s] [Sleep 10-15s] [Merge ~2s]
                                                        ↓ (chờ xong mới chạy tiếp vì async=1)
Chunk 2:  .........................[LLM Extract ~7s] [Sleep 10-15s] [Merge ~2s]
                                                                                ↓
Chunk 3:  ................................................[LLM Extract ~7s] [Sleep 10-15s]...

→ Mỗi chunk mất ~20-25 giây, chạy tuần tự từng cái một!
```

### 3.2 Ba "Kẻ Giết Thời Gian" chính

#### 🐌 Bottleneck #1: Sleep 10-15 giây sau MỖI LLM call

```python
# Trong rotating_ollama_model_complete:
await asyncio.sleep(random.uniform(10.0, 15.0))  # ← CHỖ NÀY
```

Mục đích ban đầu: tránh rate limit API. Nhưng **quá thận trọng** — mỗi chunk phải đợi 10-15 giây dù API chưa bị limit.

| Số chunks | Thời gian ngủ |
|-----------|---------------|
| 100 | ~21 phút |
| 500 | ~104 phút |
| 1000 | ~208 phút |

#### 🐌 Bottleneck #2: `llm_model_max_async=1`

```python
rag = LightRAG(
    llm_model_max_async=1,  # ← CHỈ 1 LLM CALL CÙNG LÚC
    ...
)
```

Dù LightRAG hỗ trợ chạy song song nhiều LLM call, config hiện tại **bắt chạy tuần tự**. Với 4 API keys nhưng chỉ dùng 1 tại 1 thời điểm → lãng phí 3 keys.

#### 🐌 Bottleneck #3: LLM Entity Extraction cho mỗi chunk

Bước `_process_extract_entities` gọi LLM để trích xuất entities/relationships từ **từng chunk** văn bản. Đây là bước không thể bỏ qua (cần LLM), nhưng bị chậm thêm do 2 bottleneck trên.

### 3.3 Ước tính thời gian

Giả sử 94 documents → ~500 chunks:

| Thành phần | Config hiện tại | Sau tối ưu |
|---|---|---|
| LLM extract (500 chunks × 7.5s) | ~62 phút | ~16 phút (async=4) |
| Sleep throttle (500 × 12.5s) | **~104 phút** | ~12 phút (sleep=1-2s) |
| Merge/summarize LLM calls | ~30 phút | ~10 phút |
| Embedding + DB upsert | ~10 phút | ~10 phút |
| **TỔNG** | **~3.5 tiếng** | **~48 phút** |

---

## 4. Hướng Dẫn Cấu Hình Đúng

### 4.1 Khởi tạo LightRAG đầy đủ tham số

Thay đổi cell khởi tạo `LightRAG` trong notebook:

```python
rag = LightRAG(
    working_dir=WORKING_DIR,

    # ═══ FIX 1: Đặt workspace để node label có ý nghĩa ═══
    workspace="legal_vn",

    # ═══ FIX 2: Tăng async để chạy song song ═══
    llm_model_max_async=4,          # Bằng số API keys

    # ═══ FIX 3: Set ngôn ngữ tiếng Việt ═══
    addon_params={
        "language": "Vietnamese",
        "entity_types": [
            "person", "organization", "concept",
            "location", "event", "law", "regulation"
        ],
    },

    vector_storage="MilvusVectorDBStorage",
    graph_storage="Neo4JStorage",
    llm_model_func=rotating_ollama_model_complete,
    llm_model_name="gpt-oss:120b-cloud",
    embedding_func=EmbeddingFunc(
        embedding_dim=768,
        max_token_size=256,
        func=custom_hf_embedding,
    ),
)
```

### 4.2 Bảng tham số quan trọng

| Tham số | Giá trị cũ | Giá trị mới | Tác dụng |
|---------|-----------|-----------|----------|
| `workspace` | *(không set)* → `""` | `"legal_vn"` | Node label = `legal_vn` thay vì `base` |
| `llm_model_max_async` | `1` | `4` | 4 LLM calls chạy song song |
| `addon_params.language` | *(không set)* → `"English"` | `"Vietnamese"` | Description hoàn toàn tiếng Việt |
| `addon_params.entity_types` | *(mặc định chung)* | Custom legal types | Entity types phù hợp pháp luật VN |

---

## 5. Hướng Dẫn Tối Ưu Tốc Độ

### 5.1 Giảm sleep throttle

Trong hàm `rotating_ollama_model_complete`, thay đổi:

```python
# ❌ CŨ: Ngủ 10-15 giây — quá lâu
await asyncio.sleep(random.uniform(10.0, 15.0))

# ✅ MỚI: Ngủ 1-2 giây — đủ để tránh rate limit với 4 keys
await asyncio.sleep(random.uniform(1.0, 2.0))
```

> **Giải thích:** Với 4 API keys xoay vòng + `llm_model_max_async=4`, mỗi key chỉ nhận ~1 request/giây. Hầu hết API providers cho phép 10-60 requests/phút/key, nên sleep 1-2s là đủ an toàn.

### 5.2 Tăng BATCH_SIZE

```python
# ❌ CŨ
BATCH_SIZE = 20

# ✅ MỚI: Tăng lên 50 để giảm overhead merge giữa các lô
BATCH_SIZE = 50
```

### 5.3 Tổng hợp thay đổi tốc độ

```
TRƯỚC TỐI ƯU:                        SAU TỐI ƯU:
──────────────                        ────────────
async=1, sleep=10-15s                 async=4, sleep=1-2s

Chunk 1: [====][zzzzzzzzzzz]          Chunk 1: [====][z]
         Chunk 2: [====][zzzzzzzzzzz] Chunk 2: [====][z]
                  Chunk 3: ...        Chunk 3: [====][z]
                                      Chunk 4: [====][z]
↑ Tuần tự, mỗi cái đợi rất lâu       ↑ 4 cái chạy cùng lúc, ít đợi

~3.5 tiếng                            ~45 phút
```

---

## 6. Checklist Trước Khi Chạy

### Bước 1: Xác nhận môi trường

- [ ] Đã cài `lightrag-hku`, `sentence-transformers`, `pymilvus`, `neo4j`, `ollama`
- [ ] GPU khả dụng cho HuggingFace Embedding (kiểm tra `device: "cuda"`)
- [ ] Milvus Cloud URI + Token hợp lệ
- [ ] Neo4j Aura URI + credentials hợp lệ
- [ ] Các API keys Ollama Cloud còn quota

### Bước 2: Xác nhận dữ liệu

- [ ] `metadata.csv`, `relationship.csv`, `content.csv` đã upload lên Kaggle datasets
- [ ] `output_link_sohieu.txt` đã upload
- [ ] Chạy Giai đoạn 1 (cells 1-20) để xuất `custom_kg_full.json`
- [ ] Kiểm tra `custom_kg_preview.json` có entities, relationships, chunks hợp lệ

### Bước 3: Cấu hình LightRAG

- [ ] Đã set `workspace="legal_vn"` (hoặc tên workspace mong muốn)
- [ ] Đã set `addon_params={"language": "Vietnamese", ...}`
- [ ] Đã set `llm_model_max_async=4`
- [ ] Đã giảm `asyncio.sleep` xuống `1.0-2.0` giây
- [ ] Đã tăng `BATCH_SIZE` lên `50`

### Bước 4: Chạy và theo dõi

- [ ] Chạy cell `await main()`
- [ ] Theo dõi log: mỗi lô (batch) sẽ in progress
- [ ] Nếu gặp rate limit → tăng sleep lên `3.0-5.0` giây
- [ ] Sau khi hoàn tất, kiểm tra Neo4j Browser:
  - Nodes có label `legal_vn` (không phải `base`)
  - Description bằng tiếng Việt
  - Properties entity_type có giá trị hợp lệ

### Bước 5: Xác nhận kết quả

Chạy truy vấn Cypher trên Neo4j Browser:

```cypher
-- Đếm nodes
MATCH (n:`legal_vn`) RETURN count(n) AS total_nodes;

-- Đếm relationships
MATCH (:`legal_vn`)-[r:DIRECTED]-(:`legal_vn`) RETURN count(r) AS total_rels;

-- Xem sample node
MATCH (n:`legal_vn`) RETURN n LIMIT 5;

-- Xem sample relationship
MATCH (a:`legal_vn`)-[r:DIRECTED]-(b:`legal_vn`)
RETURN a.entity_id, r.keywords, r.description, b.entity_id
LIMIT 5;

-- Thống kê entity types
MATCH (n:`legal_vn`)
RETURN n.entity_type, count(*) AS cnt
ORDER BY cnt DESC;
```

---

## Phụ Lục: Kiến Trúc Lưu Trữ LightRAG

```
                    ┌──────────────────────┐
                    │     LightRAG Core    │
                    │   (lightrag.py)      │
                    └──────────┬───────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
   ┌────────▼────────┐ ┌──────▼──────┐ ┌────────▼────────┐
   │   Vector DB     │ │  Graph DB   │ │    KV Store     │
   │   (Milvus)      │ │  (Neo4j)    │ │  (JSON/Redis)   │
   ├─────────────────┤ ├─────────────┤ ├─────────────────┤
   │ entities_vdb    │ │ nodes:      │ │ text_chunks     │
   │ relationships_  │ │  label=     │ │ full_docs       │
   │   vdb           │ │  workspace  │ │ full_entities   │
   │ chunks_vdb      │ │             │ │ full_relations  │
   │                 │ │ edges:      │ │ llm_response_   │
   │ (embeddings     │ │  type=      │ │   cache         │
   │  + metadata)    │ │  DIRECTED   │ │                 │
   └─────────────────┘ └─────────────┘ └─────────────────┘
```

### Node Properties trong Neo4j

| Property | Mô tả | Ví dụ |
|----------|--------|-------|
| `entity_id` | ID duy nhất (= entity name) | `"Tài Sản Chung"` |
| `entity_type` | Loại entity | `"concept"` |
| `description` | Mô tả (do LLM sinh ra) | `"Tài Sản Chung là tài sản chung của vợ chồng..."` |
| `source_id` | Chunk ID nguồn | `"chunk_01/2016/TTLT_7"` |
| `file_path` | Số hiệu văn bản gốc | `"01/2016/TTLT-TANDTC-VKSNDTC-BTP"` |
| `created_at` | Timestamp tạo | `1776885931` |

### Relationship Properties trong Neo4j

| Property | Mô tả | Ví dụ |
|----------|--------|-------|
| `description` | Mô tả quan hệ | `"Hoàn Cảnh Gia Đình là yếu tố xem xét..."` |
| `keywords` | Từ khóa phân loại | `"circumstance, division factor"` |
| `weight` | Trọng số quan hệ | `1.0` |
| `source_id` | Chunk ID nguồn | `"chunk_01/2016/TTLT_7"` |
| `file_path` | Số hiệu văn bản gốc | `"01/2016/TTLT-TANDTC-VKSNDTC-BTP"` |
