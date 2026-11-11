# Profile OrcaSlicer przeniesione do osobnego repozytorium

**[Zortrax-m300-Orca-Slicer](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer)** jest jedynym miejscem dalszego rozwoju profili drukarki, procesu i materiałów, testów slicera oraz raportów G-code.

Przeniesiono kompletny katalog Orca ze źródłowego commita `1f58160e2d0e81c462648e57fa0ee69123313a4f`. Profil R3 w nowym repozytorium jest identyczny bajt w bajt (SHA-256 `3b60cd1ec9d324d5c2ed5a2aec7ced13560d13eff56734167bede1655e4333a4`). Kopię wszystkich 11 źródłowych plików, ich sumy i raporty R2/R3 zachowano w nowym repozytorium. Nowy niezależny test OrcaSlicer 2.3.2: 17 profili PASS, 0 błędów, test przekazywania PA PASS. Z-PEEK pozostaje tylko katalogiem; testy GUI i sprzętu nie zostały wykonane.

Tutaj pozostają **host Klippera, firmware MCU, OLED/Fluidd, implementacje START_PRINT/END_PRINT/PAUSE, procedury, limit nastawy stołu i instalatory**. Nie zmieniono ich podczas porządkowania. Profil Orca wywołuje te funkcje, ale ich nie instaluje.

Usunięto aktywny katalog `orca/`, workflow slicera oraz jednorazowy skrypt łączący poprawki hosta i profili. Testy hosta R3 są niezależne w `m300-r3-host-audit.yml`. Wdrożone źródła hosta są utrzymywane bez generatora `apply_m300_r3.py`.

Historia Git i stare commity nie są przepisywane. PR #13 jest zastąpiony nowym repozytorium; PR #14 dotyczy już wyłącznie hosta i kontroli temperatur. Rozdzielenie repozytoriów nie jest instalacją na Orange Pi ani zatwierdzeniem sprzętowym R3.
