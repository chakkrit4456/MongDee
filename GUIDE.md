# คู่มือการใช้งาน MONGDEE AI Booth OS

คู่มือติดตั้งและรันแบบสั้น ๆ ตั้งแต่โคลนโปรเจกต์จนเปิดใช้งานได้ (รายละเอียดเชิงลึกดู [README.md](README.md))

## 1. โคลนโปรเจกต์

```bash
git clone https://github.com/chakkrit4456/MongDee.git
cd MongDee
```

## 2. ติดตั้ง


### แบบ command line (นักพัฒนา)

```bash
python3 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

## 3. วิธีรัน

เปิด virtual environment ก่อนทุกครั้ง (`source .venv/bin/activate` หรือ Windows: `.venv\Scripts\activate`)

### ผ่านเบราว์เซอร์ (แนะนำ — ครบทุกฟีเจอร์ในหน้าเว็บเดียว)

```bash
python web_server.py
# เปิดเฉพาะเครื่องนี้: http://127.0.0.1:8000/

python web_server.py --host 0.0.0.0 --port 8000
# ให้อุปกรณ์อื่นในวง LAN เดียวกันเข้าถึงได้ด้วย (เช่น แท็บเล็ตหน้าบูธ)
# เปิดจากอุปกรณ์อื่น: http://<IP เครื่องที่รัน>:8000/
```

ตัวเลือกเพิ่มเติม: `--booth-id`, `--booth-name`, `--event-id`, `--cameras /dev/video0,/dev/video2` (ไม่ระบุ = ค้นหากล้องอัตโนมัติ), `--no-open` (ไม่เปิดเบราว์เซอร์อัตโนมัติ)

หน้าเว็บที่ได้: `/booth` (สตรีมกล้องสด + ปุ่มเต็มจอ/เปิดกล้องแยกหน้าต่างต่อจอ), `/product-view` (ดูรายละเอียดสินค้าที่สแกนเจอ แยกหน้าต่างต่างหาก), `/dashboard` (วิเคราะห์ข้อมูล), `/trainer` (เทรน AI ให้รู้จักสินค้า) — เปิดพร้อมกันหลายแท็บ/หลายอุปกรณ์/หลายจอได้

### แบบ Desktop (PySide6)

```bash
python launcher.py                          # หน้าต่างเดียว มีปุ่มเปิดทุกโหมด
python app.py --cameras /dev/video0,/dev/video2   # เปิดบูธตรง ๆ
python dashboard.py                         # เปิด Dashboard แยก
python trainer.py                           # เปิด AI Trainer แยก
```

### สร้างไฟล์ .exe/executable ตัวเดียว (แจกให้คนอื่นใช้)

```bash
bash build_linux.sh        # Linux
build_windows.bat          # Windows
```
ดูรายละเอียดที่ [BUILD.md](BUILD.md)

## 4. เริ่มใช้งานสินค้าจริง

แคตตาล็อกสินค้าเริ่มต้นว่างเปล่า — เข้าหน้า `/trainer` แล้ว "เพิ่มสินค้าใหม่" (กรอกชื่อ/แท็กไลน์/ราคา/รายละเอียด/FAQ) จากนั้นอัปโหลดรูป/วิดีโอ หรือใช้ปุ่ม "บันทึกจากกล้อง" ให้ระบบเก็บภาพจากกล้องสดให้อัตโนมัติ
