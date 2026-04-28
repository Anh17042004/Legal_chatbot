# Workflow Search Mode: GLOBAL

`global` là chế độ tìm kiếm **tri thức tổng quan, thiên về các MỐI QUAN HỆ (Relationships)** giữa các thực thể mà Graph DB có thể mang lại. Mode này hiệu quả đối với các câu hỏi phức tạp yêu cầu cái nhìn bao quát về nguyên nhân - kết quả.

## Luồng hoạt động (Workflow)

1. **LLM Keyword Extraction (Chỉ lấy High-level):**
   Hệ thống gọi LLM phân tích câu hỏi để bóc ra `high-level keywords` - thường là các động từ, mối quan tâm lớn, hành vi vi phạm, quy tắc chung (VD: "Quy tắc nhường đường", "Khung hình phạt", "Tham gia giao thông").

2. **Relationship Vector Search:**
   Lấy bộ từ khóa trên gộp lại, mã hóa thành Vector và chọc thẳng vào `Relationships VectorDB`. 
   Thay vì tìm các Node cụ thể, ở đây đi tìm các **CẠNH (Edges)**. Các cạnh luôn kèm theo `Description` mô tả ý nghĩa kết nối giữa hai Node.

3. **Graph Traversal (Lấy chùm Nodes & Chunks quanh cạnh đó):**
   Từ Cạnh tìm được trên Neo4j (VD: Cạnh `[Tuân_thủ]`), hệ thống truy xuất đồng thời 2 Node ở đầu tựa cạnh đó, bao gồm thông tin chi tiết của Cạnh + những đoạn văn gốc sinh ra cạnh này.

4. **Token Truncation:**
   Kiểm soát độ dài, cắt bỏ các quan hệ xa/ kém chính xác nếu vượt `max_relation_tokens`.

5. **Sinh câu trả lời (LLM Generation):**
   Cung cấp cấu trúc Context chứa các hành động, chuỗi liên kết để LLM có tầm nhìn lớn trả lời tổng quan vấn đề.

---

## Ví dụ cụ thể

**Câu hỏi người dùng:** *"Những hành vi nào bị nghiêm cấm trong Luật Giao thông đường bộ?"*

- **Bước 1:** LLM móc ra:
  - High-level: `["hành vi nghiêm cấm", "pháp luật giao thông", "luật giao thông đường bộ"]`

- **Bước 2 (Relationship Search):**
  Hệ thống đi tìm Cạnh (Edge) có liên kết diễn tả chữ `Nghiêm_cấm` hoặc `Vi_phạm`. 
  
- **Bước 3 (Neo4j Retrieve):**
  Trích xuất ra được hàng loạt các Cạnh:
  - `[Người tham gia] --(Bị nghiêm cấm)--> [Bấm còi gây ồn ào]`
  - `[Người điều khiển] --(Bị nghiêm cấm)--> [Sử dụng rượu bia]`
  - `[Bộ tham mưu] --(Trình bày)--> [Luật Giao Thông]` (Mạng lưới khái quát cực lớn).

- **Bước 4 & 5:**
  Xây dựng một Context chứa một loạt những hành vi rải rác gắn liền với từ khóa "Cấm". LLM sẽ tổng kết lại một đáp án trả lời đầy đủ hoàn chỉnh theo dạng danh sách. Mặc dù các Chunk phân bố ở những trang luật khác nhau, nhờ Graph Relation, chúng gom lại được vào một câu trả lời duy nhất.
