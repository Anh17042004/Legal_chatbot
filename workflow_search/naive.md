# Workflow Search Mode: NAIVE

`naive` là chế độ search RAG (Retrieval-Augmented Generation) truyền thống và cơ bản nhất. Trong chế độ này, LightRAG **hoàn toàn không sử dụng Knowledge Graph (Đồ thị tri thức Neo4j)** cũng như không mồi LLM tạo từ khóa trước. Nó chỉ dựa vào Vector Search trực tiếp.

## Luồng hoạt động (Workflow)

1. **Embedding câu hỏi:**
   Hệ thống lấy toàn bộ chuỗi text câu hỏi của người dùng và chuyển thành một chuỗi số Vector (Embedding) duy nhất.

2. **Vector Similarity Search (Tìm kiếm độ tương đồng vector):**
   So khớp vector của câu hỏi với toàn bộ các chunk văn bản nằm trong Text Chunks VectorDB (Milvus/Qdrant/Faiss...). 
   Các đoạn văn bản có độ tương đồng ngữ nghĩa cao nhất (Cosine Similarity) sẽ được lựa chọn.

3. **Get Top K Chunks:**
   Lấy ra đúng số lượng đoạn văn quy định trong biến `chunk_top_k` (Ví dụ 20 chunks).

4. **Trực tiếp sinh câu trả lời (LLM Generation):**
   Ghép 20 chunks văn bản này thành khối Context gửi cho LLM (cùng với System Prompt) để sinh ra câu trả lời.

---

## Ưu điểm và Nhược điểm

*   **Ưu điểm:** Tốc độ phản hồi rất nhanh, tiết kiệm chi phí số token do bỏ qua bước LLM Extract Keywords, tốn ít tài nguyên phần cứng. 
*   **Nhược điểm:** Mất hoàn toàn cấu trúc liên kết luật. Rất dễ lấy sai ngữ cảnh nếu trong câu hỏi có nhiều từ bóng gió, cụm từ địa phương không xuất hiện chính xác trong văn bản luật ("trèo vỉa hè" thay vì "điều khiển xe trên hè phố").

---

## Ví dụ cụ thể

**Câu hỏi người dùng:** *"Trích dẫn cho tôi Điều 30 Nghị định 100/2019/NĐ-CP"*

- **Bước 1:** Câu hỏi được đem thành Vector.
- **Bước 2 & 3:** Quét trong Vector DB, hệ thống thấy rằng những chunk đầu tiên nói về "Điều 30" của văn bản "Nghị định 100" có độ tương hợp vector gần như 0.99. Hệ thống móc đúng 5 đoạn văn miêu tả điều 30 đó lên.
- **Bước 4:** Gửi thẳng vào LLM. LLM trích luật ra dễ dàng.
*(Câu hỏi đóng mang tính chất truy vấn văn bản trực diện thường cực kì phù hợp với Naive)*
