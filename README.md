# lip-house-kit — ชุดโรงงานซับไตเติล + เสียง (Lip's house kit)

Public mirror ของสูตรมาตรฐานบ้าน: presets, glossary, schemas, shared tools,
factory pipelines. **ไม่มีคีย์ ไม่มีงานลูกค้า ไม่มีไฟล์เสียง/เพลง/วิดีโอ**
(.gitignore บล็อกไว้ — ใน repo มีแค่ลายนิ้วมือ SHA กับลิงก์ที่มา)

## หลักการ (Lip-locked)

1. เสียงต้นฉบับเดียวกัน เรนเดอร์กี่คลิปต้องได้เสียงเท่ากัน (วัดด้วยตัวเลข)
2. ติดตรงไหนหยุดดังๆ ห้ามเดาต่อ ห้ามเบิร์นขยะออกจอ
3. บทพูดจริงผ่านหูคนก่อนเบิร์นเสมอ
4. เจอคำยืมในบท เช็กตัวตัดคำก่อนเบิร์น

## โครง

- `presets/house.yaml` — สูตรกลาง (LUFS/ฟอนต์/เรขาซับ/gate) เปลี่ยนที่นี่ที่เดียว
- `glossary/` — loanword_dict.json (คำยืม+เกราะกันหั่น) + Prompt-Bold (OFL)
- `schemas/` — work-order / manifest / checks (JSON schema ไฟล์ส่งกันระหว่างโรง)
- `tools/` — vo_ingest / mix_bgm / qa_batch / drive_upload / drive_delete
- `factories/subtitle/pipeline.py` — ใบสั่งซับเข้า → คลิปติดซับออก
- `factories/audio/pipeline.py` — เสียงกลาง+คลิป+เพลงเข้า → มาสเตอร์ออก
- `factories/scout/` — make_contact.py (contact sheet + metrics) + RUNBOOK
  (ขั้นคนตัดสิน) — ฟุตดิบเข้า → ตารางช็อต + ใบสั่งตัดออก
- `factories/edit/pipeline.py` — ใบสั่งตัดเข้า → เบสคลิปออก
  (ห้าม zoompan ตามกฎบ้าน)
- `factories/review/review_job.py` — AGY ดูวิดีโอเตรียมบท+ธงให้คนชี้ขาด
  (AGY ห้ามล็อกบท) — วิดีโอเข้า → ร่างบท + uncertain list ออก
- `factories/qa/pipeline.py` — ไฟล์ไฟนอลเข้า → คำตัดสิน + ส่ง Drive
  (QA เฟรม + มิเตอร์ + ประตูเสียง, deliver ปิดเป็นค่าเริ่มต้น)
- `renderer/` — สมองเบิร์นซับ (เทสต์ 162 ข้อ)

## เริ่มใช้ (Windows: Python 3.10+, ffmpeg)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r renderer/requirements.txt
copy NUL .env  # then put GROQ_API_KEY inside (never commit it)
.\.venv\Scripts\python.exe -m pytest renderer/tests -q  # must be 162 passed
```

โรงซับ 1 คลิป: เขียน work-order.json → `python factories/subtitle/pipeline.py
work-order.json out/` → ได้คลิป + รายงาน (gate ไหนตก = หยุดพร้อมเหตุผล)

โรงเสียง 1 คลิป: `python ..\tools\vo_ingest.py voice.mov canonical\`
(ครั้งเดียว) → เขียน audio-order.json →
`python factories/audio/pipeline.py audio-order.json out\`

เพลงหลัก (Pixabay, โหลดเอง): piano-corporate-482783 (main),
piano-motivational-148119 (alt) — กด -20dB ใต้เสียงพากย์ตาม presets
