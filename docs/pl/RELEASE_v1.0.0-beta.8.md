# M300 Classic v1.0.0-beta.8 — logo Klippera i sygnały menu

Zmieniono ikonę pozycji **Klipper** w menu OLED: zamiast zwykłej litery K
jest oryginalny znak Klippera przypominający literę V zakończoną dyszą.
Zachowano układ drukarki oraz ruchomą ikonę głowicy u góry. Oryginalny
znak został odwzorowany jako bitmapa monochromatyczna 50×50 px;
źródło: [Klipper3d/klipper](https://github.com/Klipper3d/klipper/blob/master/docs/img/klipper.svg),
licencja GPL-3.0. [SVG nowej grafiki](../assets/menu-symbols/klipper-official-mark-50.svg).

Ujednolicono sygnały buzzera: **35 ms** przy zwykłym wejściu/wyjściu
i wyborze pozycji oraz **140 ms** przy pozycji Back/Up. Osobny zegar
wyłącza buzzer w wyznaczonym czasie niezależnie od odświeżania
statusu i LED co 500 ms. `Buzzer → Disabled` natychmiast wyłącza
aktywny sygnał i blokuje kolejne.

Aktualizacja ze zweryfikowanego beta.7 zachowuje profile druku, Bed Mesh,
OLED i wszystkie zabezpieczenia. Przy bezczynnej drukarce w stanie Ready
wykonaj na Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Nie wgrywaj ponownie MCU ani bootloadera. Walidacja programowa wymaga
683 testów hosta oraz pełnej kompilacji Klippera i Fluidd.
Rzeczywisty czas trwania sygnałów należy jeszcze sprawdzić na drukarce.
