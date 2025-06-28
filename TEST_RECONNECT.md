# Test Skenario untuk Sistem Reconnect

## Skenario 1: Host Reconnect
1. **Player A** host game dengan nama "Alice"
2. Server memberikan room code (misal: "123456")
3. **Player A** disconnect sebelum ada player lain yang join
4. **Player A** kembali connect dan pilih "Join Game"
5. Input nama "Alice" dan room code "123456"
6. **Expected**: Player A berhasil reconnect sebagai host dan kembali menunggu player lain

## Skenario 2: Player 2 Reconnect - Fase Placing Ships
1. **Player A** ("Alice") host game dengan room code "123456"
2. **Player B** ("Bob") join dengan room code "123456"
3. Kedua player masuk fase placing ships
4. **Player B** disconnect saat sedang menempatkan kapal
5. **Player B** reconnect dengan nama "Bob" dan room code "123456"
6. **Expected**: Player B kembali ke fase placing ships

## Skenario 3: Player Reconnect - Game Sedang Berlangsung
1. **Player A** dan **Player B** sudah mulai bermain
2. Sedang giliran **Player A** menyerang
3. **Player A** disconnect
4. **Player B** mendapat notifikasi bahwa lawan disconnect
5. **Player A** reconnect dengan nama dan room code yang sama
6. **Expected**: 
   - Player A kembali ke game state yang sama
   - Masih giliran Player A
   - Player B mendapat notifikasi bahwa lawan reconnect

## Skenario 4: Timeout Reconnect
1. **Player A** dan **Player B** sedang bermain
2. **Player A** disconnect
3. **Player A** tidak reconnect dalam 5 menit
4. **Expected**: 
   - Game otomatis berakhir
   - Player B mendapat notifikasi bahwa lawan gagal reconnect

## Skenario 5: Invalid Reconnect
1. **Player A** disconnect dari game dengan room code "123456"
2. **Player C** coba reconnect dengan nama "Alice" dan room code "123456"
3. **Expected**: Reconnect gagal karena nama tidak sesuai

## Testing Manual

### Test 1: Basic Host Reconnect
```
1. Jalankan client pertama
2. Pilih "Host Game", masukkan nama "Alice"
3. Catat room code yang diberikan
4. Tutup client
5. Jalankan client lagi
6. Pilih "Join Game", masukkan "Alice" dan room code
7. Verify: Kembali ke status hosting
```

### Test 2: Player 2 Reconnect
```
1. Host game dengan client 1 (nama "Alice")
2. Join dengan client 2 (nama "Bob", gunakan room code dari step 1)
3. Tutup client 2
4. Buka client 2 lagi
5. Join dengan nama "Bob" dan room code yang sama
6. Verify: Kembali ke fase placing ships atau phase terakhir
```

## Debugging Points
- Cek server logs untuk message disconnect/reconnect
- Verify bahwa `disconnected_players` dictionary berisi data yang benar
- Pastikan `game_id` dan `player_number` tersimpan dengan benar
- Test timeout dengan menunggu > 5 menit
