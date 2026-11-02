# Restart hosta i połączenie z MCU — R16.2

[English](../en/CONNECTION.md) · [Instalacja](INSTALL.md)

Restart usługi Klippera lub Orange Pi kończy proces hosta, ale MCU drukarki
pozostaje zasilany. Lokalny guard zatrzymuje poprzednią uzbrojoną sesję po
przekroczeniu jednosekundowego terminu heartbeat. Natywny Klipper odmawia
konfiguracji MCU będącego już w shutdown. Dlatego późniejszy jawny
FIRMWARE_RESTART mógł przywrócić połączenie. `restart_method: command` wybiera
sposób resetowania tego MCU przez UART; samo nie dodaje tej procedury odzyskania.

Port mapował już zwykły RESTART ze stanu Ready na FIRMWARE_RESTART.
Nie obejmowało to nowego procesu systemowego. R16.2 dodaje jeden odczyt guarda
po natywnej identyfikacji, przed natywną konfiguracją. W trybie native, tylko
przy `start_reason=startup`, prosi istniejący mechanizm Klippera o reset MCU, gdy:

- poprzednia skonfigurowana sesja ma kod guarda 1 — utratę heartbeat hosta; albo
- szybki restart usługi zastaje poprzednią skonfigurowaną sesję nadal uzbrojoną,
  bez błędu, przed upływem terminu heartbeat.

Aktywny błąd złącza platformy blokuje próbę. Pozostałe kody guarda, w tym błędy
ADC, jawny DISARM, natywny shutdown/M112 i nieznane kody, nadal wymagają jawnego
odzyskania przez operatora. Błędna lub brakująca odpowiedź nie uruchamia resetu
w ciemno. Nieznany shutdown zgłaszany tylko przez warstwę natywną nie jest
przeklasyfikowany jako utrata połączenia.

Próba używa natywnego `MCURestartHelper._check_restart` i wymaga
`[mcu] restart_method: command`. Instalator ustawia ten natywny sposób resetu
dla bezpośredniego UART M300, zachowując ścieżkę portu i prędkość.
Jest najwyżej jedna automatyczna próba na
proces hosta, zapisana w argumentach wewnętrznego restartu Klippy i w logu.
Nieudany reset zatrzymuje się na natywnych sprawdzeniach konfiguracji.
Nie dodano demona ponowień, pętli restartów usługi, dodatkowego odpytywania
podczas pracy, zmiany prędkości UART ani MCU. MCU R14.5 pozostaje zgodny.
Moduł lifecycle nie wydaje komend grzania, wentylatora, ruchu, odtwarzania
pozycji ani ARM. Dotychczasowa natywna inicjalizacja płyty działa po świeżym
resecie i sprawdza nowe próbki ADC/guarda; poprzednie targety i bazowanie
nie są odtwarzane.

`ZORTRAX_LINK_STATUS` zgłasza rewizję `0.13.16.2-LIFECYCLE-RECONNECT` i rekord
`startup_reconnect`. `RECOVERED` oznacza świeże Ready po automatycznym resecie;
poprzedni kod guarda pozostaje w raporcie. `NO_OLD_ACTIVE_SESSION` jest prawidłowe
przy zimnym starcie MCU. `automatic_fault_clear_codes` zawiera tylko kod 1,
`automatic_hardware_fault_clear=false`, `automatic_action_resume=false`.
Log zachowuje wpisy `M300_HOST_START_RECONNECT` i `M300_HOST_START_RECONNECTED`.

Polityka jest domyślnie włączona tylko dla natywnej płyty. Jawne wyłączenie:

```ini
[m300_lifecycle]
reconnect_on_host_start: False
```

Odbiór na drukarce, gdy grzanie i ruch są nieaktywne:

1. Potwierdź Ready, zerowe targety grzałek i R16.2 w `ZORTRAX_LINK_STATUS`.
2. Wykonaj `sudo systemctl restart klipper.service`. Powinno wrócić Ready bez
   osobnego FIRMWARE_RESTART. Odczytaj decyzję procedury odzyskania.
3. Zrestartuj tylko Orange Pi, pozostawiając drukarkę zasiloną. Potwierdź lokalny
   ekran Waiting podczas rozłączenia i automatyczny powrót do Ready.
4. Sprawdź, że targety nadal są zerowe, a XYZ wymagają ponownego bazowania.
   Potwierdź dotychczasowe działanie G28, nagrzewania Z do 180C, OLED i chłodzenia.

Walidacja programowa obejmuje 17 regresji lifecycle oraz rzeczywiste natywne
helpery restartu/konfiguracji przypiętego Klippera z symulowanymi odpowiedziami
guarda i dotychczasowe scenariusze Klippy FILEOUTPUT. CI nie wykonuje fizycznego
resetu UART ani restartu Orange Pi. To pozostają opisane powyżej testy odbioru.
