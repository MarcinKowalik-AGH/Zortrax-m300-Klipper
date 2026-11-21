# Stan wydania i prób na drukarce

Host 1.0.2 współpracuje z MCU 1.0.8. Wersje działającego egzemplarza odczytasz we Fluidd poleceniem `ZORTRAX_INFO REFRESH=0`. [Rejestr prób sprzętowych](ACCEPTANCE_REGISTER.md) podaje wynik każdej próby oraz zakres nadal wymagający potwierdzenia. [Zmiany 1.0.2](RELEASE_v1.0.2.md).

[Dokumentacja techniczna (EN)](../en/STATUS.md).

## Odbiór na konkretnym egzemplarzu

| Próba | Co zanotować |
|---|---|
| Pauza i ręczne przepłukanie na 1.0.2 | Odczytaj wersje, zatrzymaj wydruk, poczekaj na zakończenie parkowania. Przy rozgrzanej dyszy użyj Extrude i Retract. Sprawdź rzeczywisty ruch filamentu i brak ruchu XYZ. Po Resume oceń miejsce powrotu na modelu. |
| Zmiana koloru | Przy 230°C i celu 150°C sprawdź, czy menu oferuje dogrzanie i czy plik pozostaje w pauzie. Przy gorącej dyszy potwierdź wypływ, cofnij 30 mm i wybierz Resume. Oczekiwany wynik to ponowne pytanie o wypływ. Dopchnij materiał, potwierdź go i wybierz Resume. Zapisz, czy głowica wróciła do tego samego miejsca i kontynuowała plik. |
| Profil płyty | Po pomiarze zapisz profil na postoju. Po restarcie sprawdź nazwę siatki podczas START oraz pierwszą warstwę w środku i przy narożach. |
| Koniec wydruku | Zapisz wersję hosta, zakończenie pliku, opuszczenie stołu w granicach Z, pozycję parkowania i komunikat PRINTING DONE. Osobno odnotuj wynik ponownego uruchomienia modelu, jeśli go sprawdzisz. |

Każdy wynik dopisz jako nowe zdarzenie w [rejestrze](ACCEPTANCE_REGISTER.md), z odczytaną wersją i opisem konkretnej czynności.
