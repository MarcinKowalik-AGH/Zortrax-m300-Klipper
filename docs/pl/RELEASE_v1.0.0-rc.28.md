# M300 Classic RC28 — odświeżanie menu siatki na OLED

Panel pobiera z Klippera fazę pomiaru, liczbę zmierzonych punktów, temperatury zadane, błąd i nazwę profilu. Obrót pokrętła na stronie siatki oraz odświeżenie okna procedury korzystają z tego samego krótkiego odczytu. Polecenie `ZORTRAX_PAD_MESH_STATUS` i obiekt Moonrakera `m300_pad_mesh` nadal udostępniają współrzędne, obszary kontaktu, wyniki i granice ruchu dla diagnostyki i mapy we Fluidd.

W istniejącym katalogu `orange-pi`, przy bezczynnej drukarce w stanie Ready z wyłączonym grzaniem, wykonaj:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Wystarczy aktualizacja hosta. MCU tego wydania ma wersję 1.0.8. Archiwum `M300_SD.zip` służy do osobnej aktualizacji firmware. Zwykła aktualizacja hosta korzysta z obecnej instalacji Fluidd na porcie 4480. Opcja `--update-fluidd --port 4480` służy do oddzielnej instalacji plików WWW. Starsze ilustracje w instrukcji pochodzą z beta.20.

### Pomiar oprogramowania

Mediany w µs, x86-64, Python 3.13.5. Odczyt zmierzono 4000 razy, a dla ekranów uwzględniono 300 kroków po 20 krokach rozgrzewki. Przy 320 krokach na stronie siatki liczba pełnych odczytów zmalała z 960 do 0.

| Etap | RC27 | RC28 |
|---|---:|---:|
| Odczyt stanu siatki | 11,47 | 0,70 |
| Zdarzenie do zakolejkowania klatki OLED | 161,32 | 91,35 |
| To samo zdarzenie do przygotowania PNG Fluidd | 237,64 | 150,68 |

### Pomiar na drukarce

Otwórz na OLED stronę Klipper → Bed mesh i włącz podgląd OLED we Fluidd. Ustaw telefon tak, aby w jednym nagraniu było widać znacznik na pokrętle, fizyczne zaznaczenie i zaznaczenie w podglądzie. Wykonaj 20 pojedynczych kroków, naprzemiennie w obie strony, bez naciskania. Dla każdego policz klatki od osiągnięcia zapadki do pierwszej widocznej zmiany na każdym ekranie. Przy 120 kl./s jedna klatka to około 8,3 ms. Porównuj medianę i 95. percentyl dla obu ekranów, używając tej samej przeglądarki, sieci i strony menu. Ważny jest wspólny początek pomiaru dla pary ekranów.

Benchmark `ci/benchmark_mesh_panel.py` odtwarza kroki na hoście i raportuje czas przygotowania klatki do wysłania na OLED oraz obrazu PNG dla Fluidd. Pomiar optyczny obejmuje dodatkowo sprzęt drukarki, łącza i wyświetlenie obrazu w przeglądarce.
