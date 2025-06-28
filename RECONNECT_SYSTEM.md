# Sistem Reconnect untuk Battleship

## Cara Kerja

Sistem reconnect telah diimplementasikan untuk private match dengan ketentuan sebagai berikut:

### 1. Fitur Reconnect
- Hanya tersedia untuk **private match** (bukan quick play)
- Player dapat reconnect dengan menggunakan **nama yang sama** dan **room code yang sama**
- Sistem akan mempertahankan game state saat player disconnect

### 2. Skenario Reconnect

#### Host Reconnect (Saat Menunggu Player 2)
- Jika host disconnect sebelum ada player 2 yang join
- Host dapat reconnect dengan nama yang sama dan room code akan dipulihkan
- Game akan kembali ke status "waiting for player"

#### Player Reconnect (Saat Game Berlangsung)
- Player dapat reconnect pada berbagai fase:
  - **Placing Ships**: Jika disconnect saat menempatkan kapal
  - **Waiting for Opponent**: Jika sudah selesai menempatkan kapal, menunggu lawan
  - **Playing**: Jika disconnect saat game sedang berlangsung

### 3. Timeout Reconnect
- Player memiliki waktu **5 menit** untuk reconnect
- Setelah 5 menit, game akan dihentikan secara otomatis
- Lawan akan mendapat notifikasi jika player gagal reconnect dalam waktu tersukut

### 4. Cara Menggunakan
1. Untuk reconnect, gunakan menu "Join Game"
2. Masukkan **nama yang sama persis** seperti sebelum disconnect
3. Masukkan **room code yang sama**
4. Sistem akan otomatis mendeteksi reconnect dan memulihkan game state

### 5. Notifikasi
- Lawan akan mendapat notifikasi saat player disconnect
- Lawan juga akan mendapat notifikasi saat player berhasil reconnect
- Status message akan memberikan informasi yang jelas tentang kondisi reconnect

## Implementasi Teknis

### Server Side
- `GameManager.disconnected_players`: Menyimpan data player yang disconnect
- `GameManager.reconnect_to_game()`: Method untuk menangani reconnection
- `GameManager.cleanup_old_disconnections()`: Membersihkan data lama

### Client Side
- Handling message `reconnect_success` untuk berbagai fase game
- Handling message `opponent_disconnected_temp` dan `opponent_reconnected`

### Game State Preservation
- Board state, ship placement, dan turn order dipertahankan
- Player names dan room code disimpan untuk validasi reconnect
