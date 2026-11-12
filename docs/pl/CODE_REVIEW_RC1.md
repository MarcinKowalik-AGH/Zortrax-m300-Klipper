# Przegląd kodu i zakres RC1

[Instrukcja główna](../../README_PL.md) · [Spójność interfejsu](RC1_UI.md) · [Rejestr prób](ACCEPTANCE_REGISTER.md)

Punkt odniesienia: beta.24, commit 89c04d4f1c6a82b19f239b156958451e4d7fc764.
Przegląd obejmuje ścieżki OLED → makro → wspólny kontroler, osiem ustawień,
aktualizację konfiguracji, grupowanie Fluidd, publiczne wersje, pakowanie oraz
publikację. Kompilacja składniowa obejmuje źródła Python; regresje obejmują
istniejące kontrolery. Nie jest to dowód braku wszystkich możliwych błędów.

Usunięto stronę Service / Tests i martwe gałęzie native znajdujące się za
wcześniejszym return w menu. Laboratoryjne makra XY/status są tylko referencją
deweloperską, nie aktywną konfiguracją. Usunięto dawny publikator R16.12 oraz
jednorazowy workflow i trzy kopie narzędzi thermal305/105; właściwa polityka
m300_temperature_policy, aktualny migrator i jego testy pozostają zachowane.
Publikacja RC używa jednego zweryfikowanego pakietu z pełnego CI.

Nowa migracja usuwa wyłącznie rozpoznane sygnatury makr, zachowuje własne dodatki
i SAVE_CONFIG, jest idempotentna i korzysta z istniejącej kopii/rollbacku.
Frontend dodatkowo ukrywa stare wpisy testowe, ale tylko dla M300_CLASSIC.
Zmiana wersji prezentowanej nie zmienia identyfikatora MCU w protokole.

Bez zmiany pozostają: ruch, homing 2/5 mm, kontakt PC7, ujemny limit Z wyłącznie
po kwalifikacji, mesh, cztery linie rozruchowe, PAUSE/RESUME/CANCEL, temperatura,
chłodzenie ochronne, UART, szybki kanał OLED, cieniowanie/ostre ikony i skale
×1/×2/×3. Te źródła są dodatkowo objęte kontrolą SHA-256 w teście RC.

Celowo nie usunięto testów jednostkowych, referencji starego firmware, kontroli
sum, starych map temperatur ani modułów używanych przez mechanizmy zgodności.
Historyczne nazwy potrzebne do migracji i identyfikatory ABI nie są zbędnymi
sufiksami interfejsu. Wymiana ich bez potrzeby mogłaby zepsuć działające instalacje.

Warunkiem wydania są testy makr przez natywny parser, wszystkich ustawień,
nieprawidłowych poziomów jasności, braku ruchu/grzania po zmianie jasności,
ukrywania starych preferencji, migracji oraz regresji całego hosta i frontend.
Udana kompilacja nie zmienia wpisów „oczekuje na test” w odbiorze sprzętowym.

Zachowano 794 istniejące regresje hosta i dodano 18 przypadków RC1 (łącznie
812). Dodatkowe testy kontraktów sprawdzają zgodność paczek, publikatora,
katalogu makr i niezmienność chronionych źródeł ruchu oraz zabezpieczeń.
