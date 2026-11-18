# M300 Classic RC19 i MCU 1.0.6

MCU 1.0.5 przed każdym zapisem licznika wymagało wartości 0x414 z rejestru identyfikacji STM32. W drukarce pracującej bez debuggera rejestr może zwrócić zero. MCU 1.0.6 rozpoznaje obsługiwany rdzeń, pamięć 256 KiB i fabryczny rekord rewizji także podczas normalnej pracy. Host pokazuje odczyty z układu i przyczynę odroczenia. MCU sprawdza również numer seryjny, zawartość banków, ruch osi, wyjścia grzałek i czas dostępny na zapis.

Na bezczynnej drukarce w stanie Ready zainstaluj host poleceniem `python3 install-orange-pi.py` w zaktualizowanym katalogu Orange Pi. Rozpakuj `MCU/M300_SD.zip` i wgraj aplikację istniejącym bootloaderem SD. Zachowaj dotychczasowy dziennik czasu. Fluidd działa na porcie 4480. Oddzielna funkcja naprawy Fluidd używa opcji `--update-fluidd --port 4480`. Ilustracje OLED pochodzą z beta.20.

Po osiągnięciu Ready wykonaj `ZORTRAX_HARDWARE_STATUS` oraz `ZORTRAX_INFO REFRESH=0`. Sprawdź wersję MCU 1.0.6, przyrost minut fabrycznych, stan NORMALIZED i wyzerowanie flagi pending. Powtórz odczyt po normalnym wyłączeniu i włączeniu drukarki. Odbiór na sprzęcie pozostaje otwarty. [Instalacja MCU i pola licznika](MCU_FIRMWARE_1.0.6.md).
