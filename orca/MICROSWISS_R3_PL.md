# M300 Classic / Micro Swiss M2580-04 — R3

## Zakres
Jeden preset drukarki 0,4 mm i jeden proces 0,20 mm. Ekstruzja M83 pozostaje. R3 przygotowuje konfigurację do kompletnego zestawu Micro Swiss M2580-04, ale nie poświadcza jego zamontowania, szczelności, pomiaru temperatury ani kalibracji PID. Sama dysza Micro Swiss nie jest kompletnym hotendem all-metal.

## Temperatury: nastawa a próg awaryjny
- Stół: **maksymalna zadana temperatura 105°C**, a nie 105°C dla każdego filamentu.
- Zachowano istniejący próg awaryjny czujnika stołu `max_temp: 120`. Nie ustawiono go na 105, ponieważ dopuszczalna nastawa 105 nie może jednocześnie być granicą, po przekroczeniu której układ natychmiast się wyłącza. To nie jest zgoda na ustawianie 120°C.
- Hotend: zachowano limit 270°C z bieżącego hosta; profile robocze pozostają do 265°C. R3 **nie podnosi** limitów do 290/300°C i nie zmienia czujnika, ADC, grzałki, PWM, ochron MCU ani `verify_heater`.
- Nie dodano automatycznego +5/+10°C do wszystkich materiałów. Wartości drukowania po wymianie hotendu ustala się na podstawie prób temperatury i przepływu. Temperatura maksymalna hotendu nie jest temperaturą właściwą dla każdego filamentu.
- Z-PEEK pozostaje rozpoznanym, ale niedopuszczonym wpisem katalogowym. 380°C przekracza limit hosta. Flaga slicera nie jest zabezpieczeniem termicznym.

Nowy moduł `m300_temperature_policy` jest ładowany przez `m300_mcu`. Waliduje wspólne metody `set_temp` i `alter_target`: obejmuje M104/M109/M140/M190, SET_HEATER_TEMPERATURE (także wywołania z Moonraker/Fluidd), procedury, PID i przywracanie nastaw. Zaktualizowano również walidację przed startem/resume, mesh, maintenance, transportem materiału i importem Z-Code. OLED oferuje dodatkową pozycję 105°C, a nie 110/120°C. Starszy komponent Fluidd może nadal wyświetlać `max_temp=120` jako zakres czujnika; backend odrzuci każdą zadaną temperaturę stołu powyżej 105. Nie zafałszowano raportowanej konfiguracji czujnika tylko na potrzeby interfejsu.

Polecenie diagnostyczne, bez uruchamiania grzania:

```gcode
ZORTRAX_TEMPERATURE_LIMITS
```

Przykładowa oczekiwana odpowiedź po instalacji: `target_limits: extruder=270, heater_bed=105`; `sensor_shutdown_limits: extruder=270, heater_bed=120`. Niższy istniejący limit użytkownika jest zachowany. Odcięcie przez temperaturę zmierzoną i ochrona MCU pozostają niezależne. Nie nadpisano PID ani rotation_distance w istniejącym printer.cfg.

## M83 i Pressure Advance
Klipper obsługuje M83 bez konwertera Inventure. Prawidłowe M83 i M82 dają tę samą ilość filamentu; różni się zapis współrzędnej E, a nie dokładność fizyczna. Zachowano zapisywanie/przywracanie stanu parsera w procedurach hosta.

Przed START_PRINT profil jawnie zeruje PA, aby purge nie odziedziczyło wartości z poprzedniego materiału. Po START_PRINT Orca emituje PA bieżącego filamentu. W R3 ustawiono `enable_pressure_advance=1`, `pressure_advance=0`, `adaptive_pressure_advance=0`. Zero jest ustawieniem neutralnym, NIE wynikiem kalibracji. Dopiero po pomiarze należy wpisać właściwą wartość w danym filamencie. Nie należy równolegle dodawać drugiego makra, które nadpisze tę wartość.

Testowa wartość 0,035 w audycie służy wyłącznie sprawdzeniu przekazywania parametru przez slicer. Nie jest zapisana w dostarczonych profilach i nie jest rekomendacją dla drukarki.

## Kolejność strojenia po montażu
1. Zweryfikować montaż, chłodzenie radiatora, czujnik temperatury i pozycję dyszy; ponownie sprawdzić homing/mesh po zmianie wysokości mechanicznej.
2. PID przy typowej temperaturze materiału (np. 230°C to przykład dla odpowiedniego filamentu, nie uniwersalna nastawa). Stół stroić w używanym zakresie, nie podnosić grzania tylko dla testu.
3. Sprawdzić rotation_distance rzeczywistym pomiarem. Wymiana samego hotendu nie zmienia przełożenia napędu ekstrudera.
4. Temperatura, przepływ/flow ratio oraz bezpieczny maksymalny przepływ objętościowy; nie zakładać automatycznie 16–18 mm³/s.
5. Pressure Advance dla materiału, dyszy i ustalonej temperatury; potem ponowna kontrola flow i retrakcji. PA nie zastępuje retrakcji.
6. Input Shaper po pomiarze drgań (akcelerometr lub test ringing). Nie wpisywać zmyślonych częstotliwości ani podnosić od razu max_accel.

Minimum cruise ratio, limity ruchu, SCV i pozostałe ustawienia mechaniki pozostają bez zmian. Skew correction i kompensacje wymiarowe wymagają pomiarów; obsługa pomijania obiektów jest osobną funkcją i nie jest tu włączana bez testu. Adaptive Pressure Advance pozostaje wyłączone do czasu wykonania kilku kalibracji zależnych od przepływu/przyspieszenia.

## Instalacja i granice walidacji
Zmiany są na osobnej gałęzi roboczej, bez aktualizacji Orange Pi i bez flashowania MCU. Nie instalować podczas druku. Pakiet hosta zachowuje dotychczasowy instalator R16.12 z planowaniem i rollback; R3 jest dodatkiem opisanym przez `M300-R3-TARGET-LIMITS`, nie nowym obrazem MCU. Przed apply należy wskazać rzeczywisty katalog Klippera i printer.cfg oraz zatrzymać usługę. Po instalacji: STATUS i ZORTRAX_TEMPERATURE_LIMITS, następnie nadzorowana kwalifikacja sprzętu. Sam import presetu Orca nie instaluje limitów na hoście.

Źródła pierwotne: Micro Swiss M2580-04 https://store.micro-swiss.com/collections/zortrax-m200/products/all-metal-hotend-with-slotted-cooling-block-for-zortrax-m200 ; Klipper G-Codes https://www.klipper3d.org/G-Codes.html ; Pressure Advance https://www.klipper3d.org/Pressure_Advance.html ; PID https://www.klipper3d.org/Config_checks.html ; Input Shaper https://www.klipper3d.org/Resonance_Compensation.html ; Orca PA https://github.com/OrcaSlicer/OrcaSlicer/wiki/pressure_advance_calib .
