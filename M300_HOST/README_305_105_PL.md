# M300 — normalna praca305/105°C

Użytkownik potwierdził11.11.2026 test305°C hotendu/105°C stołu i normalną pracę. Status USER_REPORTED; nie deklarujemy własnego testu sprzętowego ani testów wszystkich filamentów.

Nastawy305/105; odcięcia czujników310/120. Niezależne limity ADC MCU1941/1741/3941 bez zmian, bez flashowania MCU. Przeliczniki czujników, PID, prędkości, przyspieszenia, homing180°C, makra i grafiki pozostają. Natywne grzanie/ruch działają jak wcześniej. OLED oferuje305/105; Fluidd może pokazywać próg awaryjny310/120, ale backend odrzuca nastawy ponad305/105.

## Instalacja na Orange Pi, tylko na postoju
Rozpakuj pakiet. Plan: `python3 install.py --root ~/klipper --config ~/printer_data/config/printer.cfg`. Następnie `sudo systemctl stop klipper`, ta sama komenda z `--apply`, potem `sudo systemctl start klipper`. Przy innych katalogach wskaż rzeczywiste ścieżki. Instalator aktualizuje także właściwe dołączone cfg; nie dopisuj drugiego ekstrudera. Zachowuje PID i rotation_distance oraz tworzy receipt do rollback. W razie REFUSED nie wymuszaj nadpisania nieznanych plików.

Po instalacji wywołaj `ZORTRAX_TEMPERATURE_LIMITS` i `STATUS`. Oczekiwane target_limits305/105, sensor_shutdown_limits310/120. Nie uruchamia to grzania. Import Orca nie instaluje tej aktualizacji hosta. Pakiet profili2.5.0 jest w osobnym repo.

Profile PEEK/PEI pozostają widoczne, ale400/370/360°C przekracza305; START_PRINT odrzuca taki plik przed przygotowaniem. Nie podniesiono limitu poza305 i nie wyłączono zabezpieczeń.
