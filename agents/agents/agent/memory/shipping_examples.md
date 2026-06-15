# Agent memory — verified extraction examples

Each entry is a real document whose mapping the user **verified**. Treat these as
ground-truth few-shot examples: when a similar document arrives, follow the same
field mapping. Append new verified cases below; keep them short and concrete.

---

## Example 1 — ONT Shipping "Non-Negotiable Sea Waybill" → Shipping List
Single BL, 12 ISO tanks (20'TK), DG liquid cargo. Verified 2026-06-08.

### Header
| Field | Value |
|---|---|
| Vessel | FU HAI SHENG |
| Voyage No | 2603S  *(no header field → put in BL remarks)* |
| Shipping Line | ONT SHIPPING *(no header field → BL remarks)* |
| external_ref (BL/SWB No) | ONL2605008 |
| Origin (Port of Loading) | Lianyungang Port, China |
| **Destination (Place of Delivery)** | **Balikpapan** — NOT Tarakan (transship) |
| Sandaran (lokasi sandar) | Balikpapan |
| Volume | 116 *(from voyage schedule, not on the SWB)* |
| ETD / date / BL date | 2026-05-08 |
| ETA | 2026-06-06 *(from voyage schedule, not on the SWB)* |

### BL (1 row)
| Field | Value |
|---|---|
| bl_no | ONL2605008 |
| bl_date | 2026-05-08 |
| shipper | China Jiangsu International Chemical Co., Ltd |
| consignee / customer | PT Energi Unggul Persada |
| cargo / goods_description | Sodium Methylate 30% Solution — Class 3(8) UN1289 PG III, HS 2905.19 |
| no_containers | 12 |
| weight | 270,000 KGS (300 CBM) |
| freight_terms | PREPAID |
| remarks | Voyage 2603S; Line ONT SHIPPING; transshipped at Tarakan; Vol 116 |

### Containers (12 — all ISO tank 20'TK, bl = ONL2605008)
```
FLNU5040367  FLNU5040243  FLNU5040182  FLNU5040048
FLNU5039849  FLNU5040310  FLNU5040270  FLNU5040372
FLNU5040393  FLNU5039685  FLNU5039957  FLNU5040032
```
On the PDF each reads `FLNU5040367/126734/20TK` = container_no / seal_no / size.
Store container_no only; seal_no = middle group; 20TK = 20-foot ISO tank.

### Lessons reinforced
1. **Destination = Place of Delivery (Balikpapan)**, not Port of Discharge
   (Tarakan was only a transshipment hub — remark "CARGO TRANSSHIPPED AT TARAKAN").
2. Container type **ISO** is implied by `20'TK` (20-foot tank container).
3. **ETA** and **Volume** were not on the document; they came from the schedule.
