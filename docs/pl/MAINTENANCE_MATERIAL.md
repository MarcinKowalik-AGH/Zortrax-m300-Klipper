<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | MAINTENANCE_MATERIAL.md - Opisuje ręczny przesuw filamentu po operacjach materiałowych. -->
# Ręczne podawanie i cofanie filamentu

W pauzie poczekaj, aż drukarka zakończy ruch. Przy zmianie koloru poczekaj na pytanie o wypływ. W panelu **Narzędzie** we Fluidd lub w zakładce **Device** w OrcaSlicerze ustaw długość i prędkość filamentu. **Extrude** podaje go, a **Retract** cofa. Możesz powtarzać ruchy przed potwierdzeniem wypływu. Wydruk wznowisz osobno przyciskiem **Resume**.

Po zmianie materiału zarówno temperatura zmierzona, jak i zadana muszą osiągać próg ekstruzji. Przy dyszy 230°C i celu 150°C wybierz **Reheat to check flow** na OLED lub **Resume** we Fluidd. Po dogrzaniu drukarka pozostanie w pauzie. Podaj materiał, sprawdź wypływ i wybierz **Confirm material flow** lub wpisz `FILAMENT_READY`. Każde przyjęte ręczne cofnięcie po potwierdzeniu ponawia pytanie o wypływ. Po kolejnym podaniu potwierdź wypływ ponownie, a następnie wybierz **Resume**.

Po samodzielnym załadunku lub wyładunku dysza pozostaje w zadanej temperaturze do ręcznego wyłączenia grzania albo upływu zwykłego czasu bezczynności Klippera. Jeśli w pauzie dysza już ostygła, ustaw temperaturę roboczą materiału i poczekaj na dogrzanie.

[Pełny opis procedur materiałowych (EN)](../en/MAINTENANCE_MATERIAL.md).
