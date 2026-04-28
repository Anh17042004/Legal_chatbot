# Workflow Search Mode: HYBRID

`hybrid` là chế độ kết hợp nhịp nhàng giữa **Local (Entity)** và **Global (Relationships)** để bao phủ Toàn bộ mạng lưới Graph Neural. Nó hoàn toàn lờ đi Naive Search Vector.

## Luồng hoạt động (Workflow)

1. **LLM Keyword Extraction (Cả Low và High-level):**
   Lấy toàn bộ Low-level và High-level Keywords.

2. **Parallel Sub-Search (Tìm song song trên Đồ thị):**
   - Chạy nhánh 1: Tìm Node thông qua `Entities Vector DB` (Giống thuật toán của mode `local`). Lấy được mảng Entity Chunks.
   - Chạy nhánh 2: Tìm Cạnh thông qua `Relationships Vector DB` (Giống thuật toán của mode `global`). Lấy được mảng Relation Chunks.

3. **Round-Robin Merge (Merge trên DB Graph):**
   Hệ thống gạt bỏ các phần tử trùng lặp đi, và trộn đan xen Cạnh và Node lại theo tỷ lệ 1:1, tạo thành một list Context ưu tiên mảng Đồ thị khổng lồ. 

4. **Token Truncation:**
   Tương tự các Mode khác, tuân thủ theo `max_entity_tokens` và `max_relation_tokens`.

5. **Sinh câu trả lời (LLM Gen):**
   Đem một mạng lưới ngữ nghĩa phức tạp giao cho LLM xử lý.

---

## Ưu điểm và Nhược điểm

*   **Ưu điểm:** Khai thác siêu hiệu quả lượng thông tin ẩn trong Knowledge Graph. Rất thông minh và suy luận tốt.
*   **Nhược điểm:** Mất đi một phần lớn sức mạnh tìm kiếm văn bản trực quan của Naive Vector Database. Sự thiếu vắng Naive có thể khiến Bot dễ bị Hallucination (Ảo tưởng) nếu Neo4j Graph triết xuất entity bị sai trong quá trình Indexing ban đầu.

---

## Ví dụ cụ thể

**Câu hỏi người dùng:** *"Tại sao người đi bộ băng qua đường sai chỗ lại bị phạt và liên đới tới các phương tiện khác như thế nào?"*
*(Đây là một câu hỏi khó, chứa chủ thể, chứa hành vi và có câu chữ không có sẵn trong văn bản pháp luật, đòi hỏi mảng Graph suy luận)*

- **Mảng Local** sẽ túm gọn được khái niệm `[Người đi bộ]`, `[Phương tiện cơ giới]`, `[Phạt hành chính]`.
- **Mảng Global** sẽ túm gọn được các Cạnh liên quan đến sự rủi ro `[Tai nạn giao thông]`, `[Trách nhiệm hình sự]`, `[Quy tắc nhường đường]`.

Hệ thống sẽ mix 2 mảng này lại, và LLM sẽ tạo ra câu trả lời phân tích được cả quy định của người đi bộ, lẫn mức xử phạt, lẫn trách nhiệm đền bù nếu gây tai nạn cho các phương tiện đang di chuyển hợp lệ.
