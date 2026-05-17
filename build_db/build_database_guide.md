# Build Database Chi Tiet Cho LightRAG Chatbot

Tai lieu nay mo ta chi tiet notebook build_database.ipynb, bao gom:

- Du lieu dau vao va cach lam sach
- Quy trinh tao chunks, entities, relationships
- Cau truc JSON output
- Quy trinh ingest vao LightRAG (Milvus + Neo4j)
- Cac diem de toi uu, giam loi va van hanh on dinh

Muc tieu cuoi cung: tao bo tri thuc co the truy van theo kieu hybrid (graph + vector) va co the trich nguon citation.

## 1) Tong quan kien truc pipeline

Pipeline gom 2 tang:

- Tang build du lieu trung gian: CSV raw -> custom_kg_full.json
- Tang ingest vao LightRAG: custom_kg_full.json -> Milvus, Neo4j, text stores

Luong tong quat:

1. Doc metadata, relationship, content, link file.
2. Chuan hoa metadata va loc content theo so hieu hop le.
3. Parse noi dung van ban thanh legal chunks + semantic sub-chunks.
4. Tao entities tu metadata.
5. Tao relationships tu bang quan he va REL_MAP.
6. Gom thanh custom_kg va xuat JSON.
7. Chuyen doi JSON sang contract du lieu cua LightRAG.
8. Nap Macro layer (entity/relation) vao graph + vector.
9. Nap Micro layer (chunks) vao text + vector, sau do cho LLM extract va merge vao graph.

## 2) Dau vao du lieu va hop dong cot

Notebook doc 4 nguon:

- metadata.csv
- relationship.csv
- content.csv
- output_link_sohieu.txt

### 2.1 metadata.csv

Thong tin ky vong:

- So Hieu
- Loai Van Ban
- Chu De
- Noi Ban Hanh
- Hieu luc (co the bi ghi thanh Hieu Luc)

Tien xu ly:

- Hop nhat cot Hieu luc bang combine_first giua Hieu luc va Hieu Luc
- Xoa cot Hieu Luc cu
- Noi them cot file_path tu output_link_sohieu.txt

### 2.2 relationship.csv

Thong tin ky vong:

- so ky hieu
- so ky hieu van ban lien quan
- moi quan he

Bang nay duoc map sang tu dien REL_MAP de sinh keywords va weight.

### 2.3 content.csv

Thong tin ky vong:

- So Ky Hieu
- Content

Sau khi doc, chi giu cac dong co So Ky Hieu nam trong metadata de dong bo voi entity layer.

### 2.4 output_link_sohieu.txt

File text 1 cot, duoc doc voi header=None va dat ten cot la file_path.
Cot nay dung de phuc vu citation va truy vet nguon.

## 3) Build chunks chi tiet

Ham lien quan:

- count_tokens(text)
- split_article_body(full_content)
- parse_to_chunks(content, so_ky_hieu)
- build_chunks(df_content)

### 3.1 Muc tieu cua tang chunk

- Chia van ban theo don vi phap ly de truy hoi chinh xac hon
- Giu context cau truc (Chuong/Muc/Tieu muc/Dieu)
- Chia nho dieu dai bang semantic chunking de embedding chat luong tot hon

### 3.2 Logic parse theo regex

Regex dung de nhan dien:

- Chuong: Chuong/CHUONG + so La Ma hoac so thuong
- Muc: Muc/MUC + so
- Tieu muc: Tieu muc/TIEU MUC + so
- Dieu: bat dau bang Dieu <so>.

Khi gap Dieu moi:

- Luu Dieu truoc do (neu co)
- Reset bo dem noi dung
- Thu thap cac dong tiep theo cho den khi gap Dieu tiep theo hoac het van ban

### 3.3 Tao chunk text va source_id

Moi Dieu tao prefix:

- [So Ky Hieu] [Chuong] [Muc] [Tieu muc]

Noi dung chunk:

- Prefix + tieu de Dieu + than noi dung

Source id co dang:

- chunk_<so_hieu>_<dieu>
- Neu 1 Dieu bi cat semantic thanh nhieu phan: chunk_<so_hieu>_<dieu>_s1, _s2, ...

Truong chunk_order_index duoc lay tu so Dieu (bo chu cai hau to neu co), de giu thu tu logic.

### 3.4 Semantic sub-chunking

Khi token cua 1 Dieu > 1000:

- Dung SemanticChunker voi embedding model huyydangg/DEk21_hcmute_embedding
- Cau hinh:
	- buffer_size = 5
	- breakpoint_threshold_type = gradient
	- breakpoint_threshold_amount = 0.75
	- min_chunk_size = 512

Neu chunker gap loi, he thong fallback ve 1 chunk goc de tranh mat du lieu.

### 3.5 Dau ra cua build_chunks

Ham tra ve 2 bien:

- all_chunks: list cac dict chunk
- doc_to_chunks_map: dict map so_hieu -> list source_id

doc_to_chunks_map rat quan trong vi duoc tai su dung trong entity va relationship de noi source provenance.

## 4) Build entities chi tiet

Ham: build_entities(filtered_meta, doc_to_chunks_map)

### 4.1 Dieu kien tao entity

Moi dong metadata tao entity neu:

- Loai Van Ban khong rong
- So Hieu hop le (khong rong, khong NaN)

### 4.2 Cach tao description

description duoc ghep tu:

- Loai Van Ban
- So Hieu
- Chu De
- Noi Ban Hanh (dang "Duoc ban hanh boi: ...")
- Hieu luc

Muc dich:

- Tang thong tin ngu nghia de vector retrieval dung ngay o tang macro

### 4.3 Cau truc entity output

Moi entity co:

- entity_name: so hieu
- entity_type: LegalDocument
- description: chuoi metadata da ghep
- source_id: join danh sach source_id chunks bang <SEP>
- file_path: duong dan tai lieu goc

Neu khong tim thay chunk cho van ban, source_id fallback ve doc_id.

## 5) Build relationships chi tiet

Ham: build_relationships(df_rels, doc_to_chunks_map)

### 5.1 REL_MAP la gi

REL_MAP map ten quan he tieng Viet -> thong tin chuan hoa:

- kw: bo tu khoa ngu nghia cho edge
- w: trong so quan he (weight)

Vi du:

- Van ban can cu -> weight cao (1.0)
- Van ban dan chieu -> weight thap hon (0.7)
- Van ban sua doi, bo sung -> weight 0.9

### 5.2 Dieu kien bo qua

Dong relationship bi bo qua neu:

- moi quan he khong ton tai trong REL_MAP
- src_id/tgt_id rong hoac NaN
- src_id == tgt_id

### 5.3 Cau truc relationship output

Moi relationship co:

- src_id
- tgt_id
- description (mau: src + dong tu quan he + tgt)
- keywords (tu REL_MAP)
- weight (tu REL_MAP)
- source_id (chuoi chunk ids cua src)
- file_path

## 6) Gom custom KG va xuat file

custom_kg gom:

- entities
- relationships
- chunks

Notebook xuat 2 file:

- custom_kg_preview.json
	- Chi chua mot phan nho de kiem tra nhanh
	- Co _stats de xem tong so records
- custom_kg_full.json
	- Chua day du du lieu
	- Dung cho buoc ingest vao LightRAG

## 7) Chuan hoa JSON theo contract LightRAG

Truoc khi ingest, notebook chuyen custom_kg sang 3 dict:

- custom_entities_dict
- custom_relations_dict
- custom_chunks_dict

### 7.1 custom_entities_dict

Key:

- entity_name

Value bo sung cac field:

- entity_id = entity_name
- content = "<entity_name>: <description>"
- file_path

### 7.2 custom_relations_dict

Key:

- "<src_id>-<tgt_id>"

Value bo sung:

- content = description
- file_path

### 7.3 custom_chunks_dict

Key:

- source_id

Value gom:

- content
- source_id
- file_path
- full_doc_id
- chunk_order_index

full_doc_id giup he thong hieu chunk nay thuoc van ban nao, phuc vu retrieval + citation.

## 8) Ingest vao LightRAG

Notebook tao LightRAG voi:

- vector_storage = MilvusVectorDBStorage
- graph_storage = Neo4JStorage
- llm_model_func = rotating_ollama_model_complete
- llm_model_name = gpt-oss:120b-cloud
- embedding_func = HuggingFace embedding 768 dim

Sau do goi:

- await rag.initialize_storages()

## 9) Macro layer va Micro layer

### 9.1 Macro layer

Ham: build_macro_layer(rag, custom_entities_dict, custom_relations_dict)

Tac vu:

- upsert entity vao entities_vdb
- upsert relationship vao relationships_vdb
- upsert node vao graph storage
- upsert edge vao graph storage

Tang nay tao "khung tri thuc" cap van ban.

### 9.2 Micro layer

Ham: build_micro_layer(rag, custom_chunks_dict)

Tac vu:

- upsert chunk text vao local text storage
- upsert embeddings chunk vao chunks_vdb
- goi LLM extraction tren chunk de rut trich them entity/relation cap vi mo
- merge ket qua extraction vao graph + vector DB

Notebook xu ly theo lo (BATCH_SIZE = 20):

- moi lo goi rag._process_extract_entities(...)
- sau do goi merge_nodes_and_edges(...) de flush ket qua len cloud

Kieu xu ly nay giam rui ro rot ket noi va de retry theo tung batch.

## 10) Co che API key rotation cho LLM

Notebook dung danh sach API_KEYS va thuan tu xoay key khi gap loi:

- 429
- quota exceeded
- too many requests

Neu loi khong phai rate limit/quota, he thong nem exception ngay.
Neu het tat ca key ma van fail, dung pipeline voi loi tong.

Luu y: notebook dang sleep random 10-15 giay sau request thanh cong de throttle.

## 11) Cau truc output mau

### 11.1 Chunk mau

{
	"content": "[123/2020/ND-CP] [CHUONG I] Dieu 1...",
	"source_id": "chunk_123/2020/ND-CP_1_s1",
	"chunk_order_index": 1,
	"file_path": "123/2020/ND-CP"
}

### 11.2 Entity mau

{
	"entity_name": "123/2020/ND-CP",
	"entity_type": "LegalDocument",
	"description": "Nghi dinh. 123/2020/ND-CP. ...",
	"source_id": "chunk_123/2020/ND-CP_1<SEP>chunk_123/2020/ND-CP_2",
	"file_path": ".../123_2020_ndcp.html"
}

### 11.3 Relationship mau

{
	"src_id": "123/2020/ND-CP",
	"tgt_id": "01/2019/QH14",
	"description": "123/2020/ND-CP can cu 01/2019/QH14",
	"keywords": "can cu, co so phap ly",
	"weight": 1.0,
	"source_id": "chunk_123/2020/ND-CP_1<SEP>chunk_123/2020/ND-CP_2",
	"file_path": "123/2020/ND-CP"
}

## 12) Cac diem de toi uu va tranh loi

### 12.1 Bao mat

- Khong hard-code token/password/API key trong notebook
- Chuyen sang bien moi truong hoac file .env
- Dam bao file secrets nam trong .gitignore

### 12.2 Duong dan va moi truong

- Notebook dang dung duong dan Kaggle (/kaggle/...)
- Neu chay local thi doi sang path du an
- Neu khong co GPU, dat embedding device = cpu

### 12.3 Data quality

- Kiem tra truoc cac cot bat buoc trong metadata/content/relationship
- Loai bo ban ghi trung so hieu neu co
- Log so dong bi skip theo tung ly do de de debug

### 12.4 Van hanh ingestion

- Dieu chinh BATCH_SIZE theo tai nguyen may va gioi han API
- Ghi checkpoint theo batch de co the resume
- Tach rieng macro ingest va micro ingest de khoanh vung loi nhanh

## 13) Checklist chay end-to-end

1. Xac nhan du lieu dau vao day du va dung schema.
2. Chay buoc build custom_kg_full.json.
3. Kiem tra custom_kg_preview.json va _stats.
4. Cau hinh bien moi truong cho Milvus, Neo4j, LLM.
5. Khoi tao LightRAG va initialize storages.
6. Ingest macro layer.
7. Ingest micro layer theo batch.
8. Kiem tra so luong node/edge/chunks sau ingest.
9. Test mot so truy van mau de xac nhan citation.

## 14) Ket qua cuoi cung cho chatbot

Sau pipeline, he thong co:

- Graph tri thuc van ban phap luat o cap macro va micro
- Vector index cho entities, relationships, chunks
- Text chunks co source_id + file_path de citation

Nho do chatbot co the:

- Truy van theo nghia (vector search)
- Suy luan lien ket van ban (graph traversal)
- Tra ve cau tra loi kem nguon tham chieu
