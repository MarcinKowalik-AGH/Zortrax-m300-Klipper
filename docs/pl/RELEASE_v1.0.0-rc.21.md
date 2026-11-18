# M300 Classic RC21 · terminy wygaszenia OLED

Przy włączonym Sleep mode drukarka liczy oba czasy od ostatniej obsługi panelu lub polecenia operatora z Fluidd. Obowiązuje ta sama reguła w stanie Ready, przy nagrzewaniu, podczas wydruku i w pauzie. Wskaźnik LED nadal sygnalizuje alarmy. Po wyłączeniu OLED pierwszy ruch albo klik pokrętła wybudza ekran i przywraca aktualny widok. Dopiero kolejny gest obsługuje menu.

W Fluidd ustaw oba suwaki w makrze OLED_TIMERS lub ZORTRAX_OLED_TIMERS. Na panelu znajdziesz je w Settings jako OLED dim time i OLED sleep time. Oba przyjmują od 1 do 60 minut. Dla `ZORTRAX_OLED_TIMERS DIM=1 SLEEP=2` ekran przygasa po minucie i całkowicie gaśnie po dwóch minutach. Księżyc pojawia się przed wyłączeniem, jeśli jest czas na animację. Jednakowe wartości powodują wyłączenie dokładnie na wspólnym progu.

Z RC20 i MCU 1.0.7 wystarczy aktualizacja hosta. Po zakończeniu druku w katalogu gałęzi orange-pi wykonaj `git pull --ff-only && sha256sum -c --quiet SHA256SUMS && python3 install-orange-pi.py`. Oba czasy zapamiętuje MCU. Polecenie `ZORTRAX_DISPLAY_STATUS` pokazuje wartości odzyskane z pamięci. Dla wcześniejszej wersji MCU pakiet aplikacji na kartę znajduje się w MCU/M300_SD.zip. Opcjonalne `--update-fluidd --port 4480` instaluje panel z suwakami na stanowisku, które jeszcze go nie ma. Historyczne ilustracje w podręczniku pochodzą z beta.20.
