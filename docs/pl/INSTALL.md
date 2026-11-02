# Instalacja artefaktu z kompilacji

[English](../en/INSTALL.md)

Artefakt dotyczy **M300 Classic** z już zainstalowanym natywnym hostem R15.5.
To nie jest obraz Inventure. Aktualizacja hosta zachowuje ustawienia printer.cfg,
zapisane PID, kalibrację ekstrudera i geometrię ruchu.

## Host Orange Pi

Rozpakuj artefakt Actions. Skopiuj z niego katalog M300_HOST_R15_6_OEM_SLEEP
z Maca do Orange Pi, a następnie sprawdź paczkę i plan:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R15_6_OEM_SLEEP" klipper@192.168.4.157:/home/klipper/
ssh klipper@192.168.4.157
cd ~/M300_HOST_R15_6_OEM_SLEEP
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Oczekuj 71 testów OK i planu z host_update R15.6.
Jeżeli rozpoznana baza się nie zgadza, zachowaj REFUSED; nie nadpisuj plików
ręcznie. Instalator odczytuje ścieżki Klippera i konfiguracji z Moonraker,
a następnie używa znanych ścieżek instalacji M300.

Między operacjami drukarki:

~~~bash
sudo systemctl stop klipper.service
python3 install.py --apply
sudo systemctl start klipper.service
~~~

Zachowaj podaną ścieżkę RECEIPT.json. Zastosowanie wymaga zatrzymanej usługi.
Po Ready sprawdź ZORTRAX_DISPLAY_STATUS, ZORTRAX_MENU_STATUS i
ZORTRAX_NATIVE_STATUS. Nowa wersja wyświetlacza to 0.2.0-M300-OEM-SLEEP,
menu 0.13.15.6-M300-NATIVE-OEM-SLEEP. Niezmieniony transport OLED może nadal
podawać wcześniejsze host_revision.

Sprawdź przygaszenie po pięciu minutach podczas pracy, księżyc/komunikat/OFF
podczas bezczynności, wybudzenie bez ukrytego wyboru i waiting przy planowanym
restarcie. Ustawienia ekranu są w ~/printer_data/config/m300_display.cfg.
Istniejące poprawne wartości są zachowywane.

Cofnięcie z dokładnego receipt, przy zatrzymanej usłudze:

~~~bash
python3 install.py --rollback /DOKLADNA/SCIEZKA/RECEIPT.json
~~~

Późniejsze zmiany są chronione przed nadpisaniem. Następnie uruchom usługę.

## MCU

Działający MCU R14.4 nie wymaga ponownego wgrywania dla tej aktualizacji hosta.
Świeżo skompilowane pliki są dostępne do odtwarzalnych kolejnych wdrożeń.

MCU/M300_R14_4_SD.zip zawiera M300APP.M3B. To **aplikacja** pod 0x08008000
dla istniejącego bootloadera M300. Bootloader nie jest zastępowany.
ELF, mapa, słownik i raport dotyczą tej konkretnej kompilacji; nie mieszaj ich
z plikami z innego commitu. CI nie wykonało próby obrazu na fizycznej drukarce.

HOST_SOURCE to pełny zestaw źródeł odniesienia. Nie jest drugim automatycznym
instalatorem i nie zastępuje powyższej aktualizacji zachowującej kalibrację.
