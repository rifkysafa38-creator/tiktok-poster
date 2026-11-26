# tiktok-poster

Mesin posting otomatis untuk skill **ekonomi-shorts**. Setelah kamu menyetujui sebuah video, Claude
mengunggahnya ke repo ini, lalu GitHub Actions mengirim video itu ke **inbox TikTok** kamu sebagai
draft. Kamu cukup buka aplikasi TikTok, tempel caption, dan tekan **Post**.

- **Tidak ada rahasia yang lewat chat.** Client secret dan token TikTok hanya disimpan di
  *GitHub Actions secrets* repo privat ini.
- **Gratis.** Memakai API resmi TikTok (Content Posting API, mode upload ke inbox).
- **Kenapa draft, bukan langsung publik?** Aplikasi developer yang belum diaudit TikTok hanya boleh
  memposting secara privat. Mode inbox membuat videomu tetap bisa dipublikasikan normal dari
  aplikasi.

## Setup (sekali saja, ±30 menit)

### 1. Buat repo privat
Di GitHub: **New repository** → nama `tiktok-poster` → **Private** → *Create* (biarkan kosong).
Lalu beri tahu Claude: *"repo sudah dibuat"*. Claude yang akan mengisi kodenya.

### 2. Daftar aplikasi developer TikTok
1. Buka **developers.tiktok.com** → login dengan akun TikTok kamu → **Manage apps** → **Connect an app**.
2. Isi nama aplikasi (misal `insight_financial poster`), ikon, kategori, dan deskripsi singkat.
   TikTok biasanya meminta URL **Terms of Service** dan **Privacy Policy**. Kalau belum punya
   website, minta Claude membuatkan halaman sederhana.
3. **Add products**:
   - **Login Kit**: platform *Web*, Redirect URI: `https://github.com/rifkysafa38-creator`
   - **Content Posting API**: aktifkan; *Direct Post* boleh dibiarkan mati.
4. **Scopes**: centang `user.info.basic` dan `video.upload`.
5. Pakai mode **Sandbox**: tambahkan akun TikTok kamu sendiri sebagai *target user*. Kalau TikTok
   tetap meminta *submit for review*, ikuti instruksinya dan jelaskan bahwa aplikasi dipakai untuk
   mengunggah video milik akun sendiri.
6. Catat **Client key** dan **Client secret** (jangan dikirim ke chat).

### 3. Isi secrets di repo
Repo `tiktok-poster` → **Settings → Secrets and variables → Actions**:

| Jenis | Nama | Isi |
|---|---|---|
| Secret | `TIKTOK_CLIENT_KEY` | Client key dari langkah 2 |
| Secret | `TIKTOK_CLIENT_SECRET` | Client secret dari langkah 2 |
| Secret | `GH_PAT` | Fine-grained token: github.com → Settings → Developer settings → Personal access tokens → *Fine-grained* → Repository access: **hanya** `tiktok-poster` → Permissions: **Secrets: Read and write** → masa berlaku 1 tahun |
| Variable | `TIKTOK_REDIRECT_URI` | `https://github.com/rifkysafa38-creator` (harus sama persis dengan langkah 2.3) |

`GH_PAT` dibutuhkan karena TikTok mengganti refresh token setiap kali diperpanjang, dan workflow
harus menyimpan token baru itu kembali ke secrets.

### 4. Hubungkan akun TikTok (sekali)
1. Buka URL ini di browser (ganti `CLIENT_KEY`; client key bukan rahasia):
   ```
   https://www.tiktok.com/v2/auth/authorize/?client_key=CLIENT_KEY&scope=user.info.basic,video.upload&response_type=code&redirect_uri=https%3A%2F%2Fgithub.com%2Frifkysafa38-creator&state=insight
   ```
2. Login dan setujui. Kamu akan diarahkan ke halaman GitHub dengan alamat berisi `?code=...`.
3. Salin nilai `code` (dari setelah `code=` sampai sebelum `&scopes` / `&state`).
4. **Segera** (kode cepat kedaluwarsa) buka repo → **Actions → Authorize TikTok (one-time) →
   Run workflow** → tempel kode → *Run*. Kalau hasilnya hijau, setup selesai.

### 5. Beri tahu Claude
*"TikTok sudah terhubung."* Claude akan mengirim satu video uji ke inbox kamu.

## Cara kerja setiap posting
1. Claude selesai membuat video dan mengirim `final.mp4` + caption ke chat.
2. Kamu cek, lalu balas **"post"**.
3. Claude membuat *release* di repo ini berisi `final.mp4` (caption ada di catatan release), lalu
   menjalankan workflow **Post to TikTok inbox**.
4. Notifikasi masuk di aplikasi TikTok → buka draft → tempel caption → **Post**.

## Perawatan
- **GH_PAT** kedaluwarsa sesuai masa berlaku yang kamu pilih. Buat baru sebelum habis.
- **Refresh token TikTok** berlaku ±365 hari dan diperpanjang otomatis setiap kali posting. Kalau
  lama tidak posting atau kamu mencabut izin di TikTok, ulangi langkah 4.
- Batas TikTok: draft yang menunggu di inbox dibatasi (kabarnya ±5 per 24 jam), jadi selesaikan
  draft lama sebelum mengirim yang baru.
