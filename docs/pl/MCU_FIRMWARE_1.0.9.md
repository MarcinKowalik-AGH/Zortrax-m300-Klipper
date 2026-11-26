# MCU 1.0.9 — opcjonalny pomiar temperatury STM32

Dotyczy wyłącznie klasycznego Zortrax M300 z STM32F103.

Zmiana dodaje identyfikator `M300_MCU_TEMPERATURE_ABI=1` i wydłuża próbkowanie
wewnętrznego kanału ADC16 do 239,5 cyklu. Przy zegarze ADC 4,5 MHz daje to
około 53,2 µs. Pola czasu próbkowania czujników dyszy i stołu pozostają bez zmian;
wewnętrzny kanał nie uczestniczy w ich nadzorze bezpieczeństwa.

Firmware jest zgodny z dotychczasowym hostem przy wyłączonym dodatku temperatury.
Aplikacja zaczyna się pod 0x08008000. Obraz nie zawiera bootloadera.

## Wgranie

1. Poczekaj na zakończoną sukcesem kompilację tej wersji w GitHub Actions.
2. Pobierz `M300_MCU_v1.0.9_SD.zip` oraz sumy SHA256 z wydania `mcu-v1.0.9`.
   Ten plik publikowany jest dopiero po zakończeniu weryfikacji.
3. Sprawdź sumę archiwum. Wypakuj `M300APP.M3B` do katalogu głównego karty SD.
4. Zakończ druk i użyj procedury aktualizacji aplikacji w posiadanym bootloaderze M300.
   Zachowaj ustawioną prędkość UART. Nie podmieniaj bootloadera.
5. Uruchom drukarkę i hosta. W logu lub `ZORTRAX_INFO REFRESH=0` sprawdź MCU 1.0.9.
6. Zainstaluj i włącz [dodatek pomiarowy](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/pl/HOST_TEMPERATURE.md).

Weryfikacja programowa obejmuje mapowanie kanału, zachowanie pól ADC pozostałych
czujników, rozdzielenie od lokalnego ADC2 oraz świeżość danych hosta. Próba
na fizycznej drukarce pozostaje do wykonania: odczyt na zimno, obserwacja wzrostu
przy nagrzewaniu elektroniki i kontrola niezmienionych odczytów dyszy oraz stołu.

Parametry nominalne sensora: [dokumentacja ST, DS5792](https://www.st.com/resource/en/datasheet/stm32f103re.pdf).
