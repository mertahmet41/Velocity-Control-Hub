# Velocity FFB nRF24L01+ Kablosuz Protokol Dokumantasyonu

Bu dokuman, Velocity FFB direksiyon ana karti (STM32F411CEU6) ile harici kablosuz aksesuarlar (direksiyon simidi tus takimi, kablosuz pedal seti, H-vites, el freni) arasindaki 2.4 GHz RF haberlesme protokolunu, paket formatlarini, katmanli mimariyi ve sisteme yeni cihaz ekleme adimlarini aciklar.

---

## 1. Donanim ve SPI2 Pin Yapilandirmasi

nRF24L01+ modulu STM32F411 uzerinde donanim SPI2 veri yoluna ve kesme pinine baglidir. Timer PWM veya enkoder pinleri ile hicbir cakismasi yoktur:

| Sinyal | STM32 Pin | Aciklama |
| :--- | :--- | :--- |
| **SCK** | **PB13** | SPI2 Seri Saat Hatti |
| **MISO** | **PB14** | SPI2 Ana Giris / Modul Cikis |
| **MOSI** | **PB15** | SPI2 Ana Cikis / Modul Giris |
| **CE** | **PB6** | Chip Enable (TX/RX Mod Kontrolu) |
| **CSN** | **PB7** | SPI Chip Select (Aktif Dusuk) |
| **IRQ** | **PB9** | Kesme Girisi (Dusuk Seviye Aktif, Dahili Pull-Up) |

### Varsayilan RF Parametreleri
- **Tasiyici Frekans:** 2476 MHz (Kanal 76 - Wi-Fi 2.4 GHz bandindaki kirliligi onlemek icin 2.483 GHz altina secilmistir)
- **Veri Hizi (Data Rate):** 1 Mbps (Dengeli menzil ve yuksek paket basarimi)
- **Cikis Gucu (PA Level):** -6 dBm (Yuksek)
- **Adres Uzunlugu:** 5 Bayt (Standart adres: `0xE7E7E7E7E7`, Eslestirme adresi: `0xB0B0B0B0B0`)
- **Dahili CRC:** 16-bit Hardware CRC (nRF24 CONFIG register)
- **Otomatik Onay (Auto-ACK):** Aktif (Dinamik ACK)
- **Yeniden Deneme:** 3 tekrar, 500 us gecikme (ARD=0x01, ARC=0x03)

---

## 2. Katmanli Yazilim Mimarisi

Sistem 4 bagimsiz katmandan olusur. Boylece FFB motor kontrol dongusu kesintiye ugramaz (non-blocking calisma garantisi):

```
+---------------------------------------------------------+
| Katman 4: Cihaz Yoneticisi (Device Manager & Fail-Safe)  |
| - 15 sn Eslestirme Modu (Pairing)                       |
| - Kalici Flash / EEPROM Cihaz Tablosu (Maks 4 Cihaz)     |
| - Sinyal Kaybi Guvenlik Nötrleme (250 ms Timeout)       |
+---------------------------------------------------------+
                            |
+---------------------------------------------------------+
| Katman 3: Mesaj Katmani (Message Protocol)              |
| - 16 Bayt Sabit Paket Formati                           |
| - Protokol Surumleme (v1)                               |
| - Dallas 1-Wire CRC8 Dogrulama                          |
+---------------------------------------------------------+
                            |
+---------------------------------------------------------+
| Katman 2: Baglanti Katmani (Link Layer)                 |
| - Paket Sira Numarasi (Sequence Tracking)               |
| - Paket Dusmesi / Tekrar Algilama                       |
| - Otomatik Yeniden Baglanma (Auto-Reconnect)            |
+---------------------------------------------------------+
                            |
+---------------------------------------------------------+
| Katman 1: Dusuk Seviye Surucu (SPI Register Driver)     |
| - SPI2 DMA / Polling Register Erisimi                   |
| - FIFO Yonetimi (RX_FIFO / TX_FIFO)                     |
+---------------------------------------------------------+
```

---

## 3. Paket Yapisi (16 Bayt Sabit Boyut)

Tum RF paketleri sabit 16 bayt uzunlugundadir. Bu sabit boyut, nRF24 modulleri arasinda paket uzunlugu uyumsuzluklarini onler ve deterministik transfer suresi saglar.

| Ofset | Alan | Tip | Aciklama |
| :---: | :--- | :---: | :--- |
| **0** | `MAGIC` | `uint8_t` | Sabit baslik belirteci: `0x57` ('W' - Wireless) |
| **1** | `VERSION` | `uint8_t` | Protokol surum numarasi: `0x01` |
| **2** | `MSG_TYPE` | `uint8_t` | Mesaj tipi (Bkz. Mesaj Tipleri Tablosu) |
| **3** | `DEV_TYPE` | `uint8_t` | Cihaz tipi (1: Tuslar, 2: Pedal, 3: Vites, 4: El Freni) |
| **4..7** | `DEV_ID` | `uint32_t` | Aksesuara ozel benzersiz 32-bit donanim kimligi (Little-Endian) |
| **8** | `SEQ` | `uint8_t` | 0..255 dongusel paket sira numarasi |
| **9..14** | `PAYLOAD` | `uint8_t[6]` | Cihaz tipine gore eksen veya buton verileri |
| **15** | `CRC8` | `uint8_t` | 0..14 baytlarinin Dallas 1-Wire CRC8 ozeti ($x^8 + x^5 + x^4 + 1$) |

### Mesaj Tipleri (`MSG_TYPE`)
- `0x01`: **TELEMETRY** — Surekli eksen ve buton durum paketi (10-50 Hz)
- `0x02`: **PAIR_REQ** — Cihazin eslesme talebi
- `0x03`: **PAIR_ACK** — Ana kartin eslesme onay paketi
- `0x04`: **HEARTBEAT** — Baglanti canli tutma paketi
- `0x05`: **UNPAIR** — Cihaz tarafindan gonderilen eslesme kaldirma talebi

### Cihaz Tipleri (`DEV_TYPE`)
- `0x01`: **DEV_WHEEL_BUTTONS** — Direksiyon simidi tus takimi (Maks 32 buton)
- `0x02`: **DEV_PEDALS** — Kablosuz pedal seti (Gaz, Fren, Debriyaj)
- `0x03`: **DEV_SHIFTER** — H-Vites veya Sirali vites kutusu
- `0x04`: **DEV_HANDBRAKE** — Analog / Dijital El Freni
- `0x05`: **DEV_BUTTONBOX** — Harici tus konsolu

---

## 4. Faydali Yuk (Payload) Formatlari

### A. Direksiyon Tus Takimi (`DEV_TYPE = 0x01`)
- **Bayt 9..10:** Tuslar 0 - 15 (`uint16_t` bit maskesi, Little-Endian)
- **Bayt 11..12:** Tuslar 16 - 31 (`uint16_t` bit maskesi, Little-Endian)
- **Bayt 13..14:** D-Pad / Rotary Enkoder 1 ve 2 (`uint8_t` + `uint8_t`)

### B. Kablosuz Pedal Takimi (`DEV_TYPE = 0x02`)
- **Bayt 9..10:** Gaz Pedali (`int16_t`, 0..4095, Little-Endian)
- **Bayt 11..12:** Fren Pedali (`int16_t`, 0..4095, Little-Endian)
- **Bayt 13..14:** Debriyaj Pedali (`int16_t`, 0..4095, Little-Endian)

### C. H-Vites Takimi (`DEV_TYPE = 0x03`)
- **Bayt 9:** Aktif Vites (0: Bosta/N, 1..7: Ileri vitesler, 8: Geri/R)
- **Bayt 10:** Debriyaj Isirma veya debriyaj butonu
- **Bayt 11..14:** Rezerv (0x00)

### D. El Freni (`DEV_TYPE = 0x04`)
- **Bayt 9..10:** El Freni Analog Pozisyonu (`int16_t`, 0..4095)
- **Bayt 11..14:** Rezerv (0x00)

---

## 5. Eslestirme (Pairing) ve Silme (Unpairing) Proseduru

### Eslestirme Akisi
1. Kullanici Velocity Control Hub uzerinden veya seri konsoldan `sys.nrfpair=15` komutunu calistirir.
2. Ana kart 15 saniyelik bir eslestirme penceresi acar. Bu sirada durum ledi zümrüt renkte yanar.
3. Yeni kablosuz aksesuar, `MSG_TYPE = 0x02 (PAIR_REQ)` iceren paketini yayinlar.
4. Ana kart paketi alir, cihazin benzersiz 32-bit ID'sini ve cihaz tipini kalici flash tablosuna kaydeder.
5. Cihaza `MSG_TYPE = 0x03 (PAIR_ACK)` paketi ile onay doner.
6. Cihaz normal telemetri moduna gecer.

### Cihaz Silme (Unpair) Akisi
1. Kullanici arayuzden cihaz yanindaki "Eslesmeyi Kaldir" butonuna tiklar veya seri porttan `sys.nrfunpair=<DEV_ID>` gonderir.
2. Ana kart ilgili ID'yi flash tablosundan siler ve bellekten cikarir.
3. Silinen cihazin verileri artik ana kart tarafindan kabul edilmez ve yoksayilir.

---

## 6. Hata Yonetimi ve Guvenlik (Fail-Safe)

1. **Paket Bozulmasi (CRC Hatasi):**
   Eger paketin CRC8 degeri tutmazsa paket derhal atilir; FFB dongusune veya girislere etki etmez.
2. **Sinyal Kaybi (250 ms Timeout):**
   Eger eslesmis bir kablosuz pedaldan 250 ms boyunca gecerli paket alinmazsa, baglanti kopmus sayilir.
   Gaz, Fren ve Debriyaj eksenleri guvenlik geregi derhal 0 (notr) durumuna cekilir.
   Bu sayede baglanti koptugunda gazin takili kalmasi veya kaza olusmasi fiziksel olarak engellenir.
3. **Modul Yoklugu:**
   Modul takili degilse surucu bunu SPI register kontrolunde algilar ve kablosuz sistemi pasife alir; USB FFB performansina sifir gecikme ekler.

---

## 7. Sisteme Yeni Bir Kablosuz Cihaz Ekleme Kilavuzu

Herhangi bir mikrodenetleyici (Arduino, STM32, ESP32, vb.) ve nRF24L01+ modulu ile sisteme uyumlu bir aksesuar uretmek icin su adimlar izlenir:

### C++ Ornek Kod (Verici Cihaz Tarafi)

```cpp
#include <SPI.h>
#include <RF24.h>

RF24 radio(9, 10); // CE, CSN pinleri
const uint64_t pipe = 0xE7E7E7E7E7LL;

// Dallas 1-Wire CRC8 Hesaplama
uint8_t calculate_crc8(const uint8_t* data, uint8_t len) {
    uint8_t crc = 0x00;
    for (uint8_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t b = 0; b < 8; b++) {
            if (crc & 0x80) crc = (crc << 1) ^ 0x31;
            else crc <<= 1;
        }
    }
    return crc;
}

// 16 Bayt Paket Gonderimi
void send_wireless_packet(uint32_t device_id, uint8_t dev_type, uint8_t seq, int16_t a1, int16_t a2, uint16_t buttons) {
    uint8_t packet[16];
    packet[0] = 0x57;       // Magic
    packet[1] = 0x01;       // Version
    packet[2] = 0x01;       // Telemetry Msg
    packet[3] = dev_type;   // 1: Wheel, 2: Pedals, 3: Shifter, 4: Handbrake
    
    // Device ID (Little-Endian)
    packet[4] = (uint8_t)(device_id & 0xFF);
    packet[5] = (uint8_t)((device_id >> 8) & 0xFF);
    packet[6] = (uint8_t)((device_id >> 16) & 0xFF);
    packet[7] = (uint8_t)((device_id >> 24) & 0xFF);
    
    packet[8] = seq;        // Sequence number
    
    // Payload (6 Bayt)
    packet[9]  = (uint8_t)(a1 & 0xFF);
    packet[10] = (uint8_t)((a1 >> 8) & 0xFF);
    packet[11] = (uint8_t)(a2 & 0xFF);
    packet[12] = (uint8_t)((a2 >> 8) & 0xFF);
    packet[13] = (uint8_t)(buttons & 0xFF);
    packet[14] = (uint8_t)((buttons >> 8) & 0xFF);
    
    // CRC8
    packet[15] = calculate_crc8(packet, 15);
    
    radio.write(packet, 16);
}
```

Bu paket formatina uyuldugu surece ana kart donanimi gelen veriyi otomatik olarak dogrular, eslestirir ve USB HID joystick raporuna gecikmesiz olarak yansitir.
