# Workflow Search Mode: MIX

`mix` là chế độ truy vấn (search) mạnh mẽ và toàn diện nhất trong LightRAG. Chế độ này kết hợp kết quả từ cả 3 luồng: Tìm kiếm thực thể (Local), Tìm kiếm quan hệ (Global), và Tìm kiếm vector văn bản thô (Naive). Nhờ đó, LLM nhận được ngữ cảnh cực kỳ bao quát, rất phù hợp cho lĩnh vực pháp luật (Legal) có tính suy luận, móc nối cao.

## Luồng hoạt động (Workflow)

1. **LLM Keyword Extraction (Trích xuất từ khóa):**
   Hệ thống gửi câu hỏi cho LLM lần đầu để bóc tách thành 2 loại từ khóa:
   - `Low-level keywords` (Các danh từ, thực thể cụ thể).
   - `High-level keywords` (Các chủ đề, bối cảnh, sự kiện khái quát).

2. **Chạy song song 3 luồng tìm kiếm (Triple Search):**
   - **Local Search:** Dùng low-level keywords để search trong VectorDB của Entities. Sau đó truy xuất vào Neo4j để lấy các Node. Trả về mảng `entity_chunks`.
   - **Global Search:** Dùng high-level keywords để search trong VectorDB của Relationships. Sau đó truy xuất vào Neo4j để lấy các Cạnh kết nối (Edges). Trả về mảng `relation_chunks`.
   - **Naive Search:** Dùng toàn bộ câu hỏi nguyên bản chuyển thành Vector, so khớp trực tiếp với VectorDB chứa các đoạn văn bản luật do chia nhỏ (Chunks). Trả về mảng `vector_chunks`.

3. **Round-robin Merge (Gộp mảng đan xen):**
   Trộn 3 mảng chunks lại với nhau theo hình thức bốc bài xen kẽ (1 của Naive, 1 của Local, 1 của Global...) và tự động lọc bỏ các chunks bị trùng lặp. Thu được mảng `merged_chunks`.

4. **Token Truncation (Kiểm soát độ dài):**
   Đếm số lượng token của `entities`, `relations` và `merged_chunks`. Nếu vượt qua giới hạn `max_total_tokens` (hoặc `max_entity_tokens`, `max_relation_tokens`), hệ thống sẽ cắt bỏ bớt phần dư thừa ở đuôi.

5. **Sinh câu trả lời (LLM Generation):**
   Đóng gói toàn bộ Context (Entities, Relations, Chunks) cùng với System Prompt, gửi cho LLM để tạo câu trả lời cuối cùng ở chế độ Streaming (hoặc trả thẳng Sync).

---

## Ví dụ cụ thể

**Câu hỏi người dùng:** *"Đi xe máy vượt đèn đỏ bị phạt bao nhiêu?"*

- **Bước 1:** LLM móc ra:
  - Low-level: `["xe máy", "đèn đỏ"]`
  - High-level: `["vượt đèn tín hiệu giao thông", "xử phạt hành chính"]`

- **Bước 2 (Triple Search):**
  - *Local:* Tìm được Entity `[Xe mô tô, xe gắn máy]`. Kéo theo các đoạn văn mô tả xe máy là gì.
  - *Global:* Tìm được Relation `[Hành vi chạy xe] -> [Vi phạm tín hiệu đèn]`. Kéo theo các đoạn văn quy định nguyên nhân, tính chất vi phạm.
  - *Naive:* Search vector gốc, moi ra được ngay đoạn thông tin *"Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với... vượt đèn đỏ"*.

- **Bước 3 (Merge):** Trộn các đoạn văn trên thành danh sách `[Đoạn quy định phạt tiền, Đoạn khái niệm vi phạm, Đoạn định nghĩa xe máy...]`.

- **Bước 4 & 5:** Gửi cho LLM. Nhờ có đủ các yếu tố (định nghĩa + hành vi + mức phạt), LLM dễ dàng trả lời chính xác, giải thích cặn kẽ và trích nguồn tin cậy.
