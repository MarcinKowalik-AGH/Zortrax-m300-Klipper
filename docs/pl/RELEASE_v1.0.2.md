# M300 Classic 1.0.2 — parkowanie po kalibracji stołu

21.11.2026. Host **1.0.2**, MCU **1.0.8**. Zastępuje 1.0.1.

Po udanej kalibracji Zortrax i potwierdzeniu jej wyniku oraz po udanym pomiarze
25 punktów Klippera głowica parkuje w narożu ustawionym w kontrolerze druku,
domyślnie **X300 Y305**. Najpierw przywracany jest zwykły układ współrzędnych.
Procedura zachowuje co najmniej **Z5 mm** prześwitu, sprawdza rozwarcie PC7
i czeka na zakończenie przejazdu. Zachowuje E i nie wykonuje nowego bazowania.
Błąd lub anulowanie pomiaru nie uruchamia parkowania kończącego udaną procedurę.

Zestaw hosta obejmuje **995 testów**. Sprawdzane są obie kalibracje oraz kolejność
odsunięcia i przejazdu XY, zwarty kontakt i naroże poza zakresem. Wyniki
programowe nie zastępują odbioru fizycznego przejazdu. Zachowane jest opuszczanie
stołu po Cancel wprowadzone w poprzedniej wersji.

## Aktualizacja

Na postoju, w stanie Ready i z wyłączonymi celami grzałek, wykonaj w klonie orange-pi:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Odczytaj `ZORTRAX_INFO REFRESH=0`: host 1.0.2, MCU 1.0.8.
Zainstalowanego MCU 1.0.8 nie trzeba ponownie wgrywać. Pełny pakiet zachowuje
`M300_SD.zip` dla drukarek wymagających tego MCU. Osobna naprawa Fluidd:
`python3 install-orange-pi.py --update-fluidd --port 4480`.

[Instalacja](INSTALL.md) · [Podręcznik](USER_GUIDE.md).
Ilustracje OLED zachowują oznaczoną historyczną bazę beta.20.
