# M300 Classic — MCU 1.0.2: oryginalne logo startowe Zortrax

[Instrukcja główna](../../README_PL.md) · [Wydanie MCU 1.0.2 i ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.2) · [Wspólne ikony RC3](RELEASE_v1.0.0-rc.3.md)

## Kolejność uruchamiania

Po przekazaniu sterowania przez istniejący bootloader aplikacja MCU inicjalizuje
OLED, pokazuje oryginalne logo **Zortrax**, a następnie ekran **Waiting for
Klipper...**. Logo pozostaje przez 2,5 s od zakończenia jego rysowania, jeśli
host nie przejmie wyświetlacza wcześniej. Po połączeniu ekran obsługuje Klipper.
Nie zmieniono ekranu wgrywania firmware ani samego bootloadera.

![Oryginalne logo — raster MCU w powiększeniu 3x](../assets/startup/zortrax_startup@3x.png)

Ilustracja jest renderem danych przesłanych przez rzeczywisty kod MCU w modelu
programowym, nie fotografią drukarki. Logo ma 160 × 40 pikseli, pozycję (48,12)
na ekranie 256 × 64 i oryginalne odcienie 4-bitowe. Nie użyto zastępczej czcionki,
skalowania bitmapy, rozmycia ani progowania. Powiększenie w instrukcji jest
całkowite, bez interpolacji.

## Źródło grafiki i czasu

Grafikę odzyskano z archiwalnego listingu oryginalnej aplikacji Inventure
1.6.1/r0323, z deskryptora `0x0802C910` i bloku `0x0802C924`. Suma SHA-256
odkodowanych 3200 bajtów odpowiada niezależnie zapisanemu wcześniejszemu audytowi:
`0082d29a88eef7515547189dedd83a7ef8b50fc32f0ab93ef307fb58439560d5`.
Fabryczny ekran używał tej samej pozycji oraz wariantu oczekiwania 2500 ms.
W tej aplikacji oczekiwanie jest nieblokujące: komunikacja, zabezpieczenia
MCU i przejęcie OLED przez hosta nadal działają.

Wzorzec i pochodzenie zapisano w [zortrax_logo_r0323.json](../assets/startup/zortrax_logo_r0323.json).
`ci/generate_startup_logo.py --check` sprawdza niezmienność zasobu i jego tablicy
ROM. Logo pozostaje oryginalną grafiką producenta, nie nową grafiką projektu.

## Pierwszeństwo połączenia i błędów

Host może przerwać logo w dowolnej fazie startu; przy szybkim połączeniu logo
może być krótkie lub niewidoczne. Nie opóźniamy inicjalizacji Klippera dla
samej prezentacji. Zatrzymanie awaryjne natychmiast wygasza nieaktualny ekran,
a bezpieczne zadanie rysuje komunikat błędu. Dodatkowe metadane błędu podczas
statycznego logo są sprawdzane co najwyżej co 100 ms. Nie odtwarzamy logo po
utracie łącza, oddaniu ekranu przez hosta ani wyczyszczeniu komunikatu.

Pozostaje bufor jednej linii 128 bajtów. Tablica logo zajmuje 3200 bajtów ROM;
nie dodano pełnoekranowego bufora RAM. Jedno wykonanie zadania nadal przesyła
najwyżej 32 bajty SPI, a 2,5-sekundowe wyświetlanie nie używa aktywnego oczekiwania.

## Aktualizacja Twojej drukarki

Zachowaj poprzednią aplikację. Przy zakończonym wydruku, bez pauzy, wyłącz
cele grzania i ostudź dyszę. Rozpakuj `M300_MCU_v1.0.2_SD.zip` i skopiuj tylko
`M300APP.M3B` do katalogu głównego karty SD obsługiwanej przez istniejący bootloader.

```bash
sudo systemctl stop klipper
```

Wykonaj wcześniej sprawdzoną procedurę aktualizacji **aplikacji** z karty SD.
Nie kasuj całej pamięci Flash, nie wymieniaj bootloadera i nie nadpisuj danych
fabrycznych. Po potwierdzonym zakończeniu usuń plik aktualizacji lub wyjmij kartę.

```bash
sudo systemctl start klipper
```

Odczytaj `ZORTRAX_MCU_STATUS`, `ZORTRAX_SETTINGS_STATUS` i `ZORTRAX_OLED_STATUS`.
Oczekuj MCU **1.0.2**, hosta **1.0.0-rc.3**, Ready, fault 0 i zgodnego UART
**750000 baud**. Host RC3 nie wymaga ponownej instalacji dla samego logo.
Nie zmieniono portu Fluidd 4480, wspólnych ikon, homingu, mesh, PID, grzałek,
chłodzenia, konfiguracji kwalifikowanego Z ani bazy upstream Klippera.

## Sprawdzenia i ograniczenia

Testy obejmują dokładne piksele logo dla ośmiu obsługiwanych prędkości UART,
czas wyświetlania, inicjalizację licznika czasu, wczesne przejęcie przez hosta,
zatrzymania w każdej fazie, wygaśnięcie sesji i brak ponownego logo po błędzie.
Kompilacja weryfikuje granice Flash/RAM i kontener M3B od adresu `0x08008000`.
Nie wykonano wgrywania ani nowego testu fizycznej drukarki w CI. Do oceny
wyglądu wykorzystaj zwykły start urządzenia; nie wywołuj awarii tylko po to,
aby sprawdzić przejście z logo. Poprzednia aplikacja pozostaje drogą powrotu
przez ten sam, sprawdzony bootloader.
