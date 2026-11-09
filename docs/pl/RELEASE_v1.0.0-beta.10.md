# Zortrax M300 Classic v1.0.0-beta.10 — grafika OLED host/MCU

Poprawiono grubość, jasność i rozmiar grafik OLED zgodnie z oryginalnymi
ikonami 50×50 wyodrębnionymi z firmware M300 Classic.

- Pełne logo Klippera wraz z napisem `klipper` pozostaje w środku ikony.
  Zachowano trzy jasności: 7 (ciemna część), 11 (akcent), 15 (napis).
- Usunięto animowany kwadracik/kreskę **pod platformą**. Sama platforma
  ma stały obrys o grubości dwóch pikseli, a animacja głowicy na górze
  pozostała.
- Ujednolicono obrysy ikon Home/Move do dwóch pikseli i pełnej jasności
  15; osie niewybrane mają poziom 9, a wybierane migają 15/3.
- MCU ma jawny format 50×50 i dodatkowy test przenoszenia trzech
  poziomów jasności 7/11/15 przez SPI bez konwersji.

**Nie zmieniałem buzzera**, jego timerów, GPIO ani czasów sygnałów.

W normalnym menu grafikę generuje Orange Pi, a MCU przesyła gotowe
4-bitowe piksele. Osobny renderer MCU dotyczy ekranów oczekiwania,
rozłączenia i błędów, zachowując istniejący kształt i jasność.
Nowe źródła MCU zostały objęte kompilacją i testami, lecz dla tych
poprawek menu nie jest konieczne ponowne wgrywanie MCU.

## Aktualizacja hosta

Przy bezczynnej drukarce i stanie Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Zachowano bazowanie X/Y, zabezpieczenia Z, geometrię stołu oraz
konfigurację Klippera. Wydanie wymaga 693 testów hosta,
testów MCU, zbudowania Klippera i Fluidd oraz pełnych Actions.
