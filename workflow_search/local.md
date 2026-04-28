# Workflow Search Mode: LOCAL

`local` là chế độ tìm kiếm **tập trung sâu vào các THỰC THỂ (Entities)** bên trong Knowledge Graph. Chế độ này bỏ qua Naive VectorDB và không quan tâm đến tầm nhìn bức tranh lớn mạng lưới. Nó dùng để tra cứu định nghĩa, đối tượng cụ thể.

## Luồng hoạt động (Workflow)

1. **LLM Keyword Extraction (Chỉ lấy Low-level):**
   Gọi LLM để lấy chỉ trích xuất các từ khóa đặc tả thấp `low-level keywords`. Đó là các danh từ, tân ngữ, tên người, sự vật, sự việc (VD: "Người đi bộ", "Xe đạp điện", "Cảnh sát giao thông").

2. **Entity Vector Search:**
   Lấy nhóm từ khóa low-level trên map thành vector và search trên `Entities VectorDB`. 
   Mục đích là tìm ra các **Entity Nodes** trong Neo4j có Description (mô tả) khớp nhất với từ khóa.

3. **Truy ngược đồ thị để lấy Context:**
   Từ danh sách các Node trúng tuyển (ví dụ lấy top 10 Node), truy xuất ngược vào Neo4j để nhặt ra các chunks document ban đầu mà đã sinh ra Node đó.
   Bên cạnh đó, các mô tả ngắn `Entities Context` cũng được gộp vào.

4. **Token Truncation:**
   Cắt giảm danh sách Nodes và Chunks nếu vượt quá `max_entity_tokens` và `max_total_tokens`.

5. **Sinh câu trả lời (LLM Gen):**
   Cấu trúc Context bao gồm: Danh sách thực thể (Định nghĩa) + Các đoạn nội dung có liên quan đến thực thể. LLM bám vào đó để trả lời.

---

## Ví dụ cụ thể

**Câu hỏi người dùng:** *"Cảnh sát giao thông có những quyền hạn gì khi dừng phương tiện?"*

- **Bước 1:** LLM móc ra:
  - Low-level: `["Cảnh sát giao thông", "dừng phương tiện", "quyền hạn"]`

- **Bước 2 (Entity Search):**
  Hệ thống đi tìm Node tên là `[Cảnh sát giao thông]`, Node `[Dừng phương tiện]`.

- **Bước 3 (Neo4j Retrieve):** 
  Sau khi tìm được Node CSGT, nó sẽ tìm trong toàn bộ kho dữ liệu tất cả những đoạn văn cụ thể, chi tiết có nói đến chủ ngữ `[Cảnh sát giao thông]`.

- **Bước 4 & 5:**
  Trộn lại và gửi lên LLM. Mô hình nhận được bản mô tả định nghĩa CSGT là ai, và các đoạn văn bản có sự kết nối trực tiếp đến chữ CSGT, cho phép LLM dễ dàng liệt kê đúng các quyền hạn.
