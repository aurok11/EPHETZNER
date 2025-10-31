## Plan: EPhemenral HETZNER VPS Builder (EPHETZNER)

### Shared To-Do
- [x] Build service layer modules (Hetzner, DuckDNS, S3, SSH) with retry/logging scaffolds.
- [x] Implement create/delete CLI commands with summaries, cloud-init handling, and backups.
- [x] Add initial tests and expand README with usage + troubleshooting notes.
- [x] Prepare packaging automation (PyInstaller script, GitHub Actions workflow, checksums).

### Cel i Zakres
- CLI zarządzana przez `uv`, konfiguracja pobierana interaktywnie i przechowywana w pamięci.
- Dystrybucja binarna przez PyInstaller z auto-detekcją systemu; workflow GitHub Actions (tagi `v*`) dostarcza artefakty Linux/Windows, sumy SHA256, ZIP źródłowy oraz automatyczny changelog.
- Architektura oparta o OOP i `abc.ABC` dla usług zewnętrznych; moduły muszą respektować te kontrakty.
- Każdy moduł posiada czytelne docstringi opisujące odpowiedzialność i publiczne API.

### Faza 1 – Szkielet projektu
- [x] Utworzyć strukturę `uv`, katalogi logiczne i podstawowe pliki konfiguracyjne.
- [x] Przygotować konwencje kodu oraz wstępny README.

### Faza 2 – Konfiguracja i interfejs użytkownika
- [x] Zaimplementować `config.py` oraz `ui/menus.py` z interaktywnymi pytaniami.
- [x] Zapewnić walidację, komunikaty błędów i formatowanie outputu Rich.

### Faza 3 – Warstwa usług
- [x] Zaimplementować Hetzner, DuckDNS, S3 i SSH z logowaniem oraz obsługą błędów.
- [x] Zapewnić testowalność poprzez adaptery i kontrakty ABC.

### Faza 4 – Komendy CLI
- [x] `commands/create.py`: interaktywny provisioning, cloud-init, integracja DuckDNS.
- [x] `commands/delete.py`: selekcja po etykietach, backup S3, potwierdzenia Rich.
- [x] `main.py`: rejestracja komend, globalny punkt wejścia Typer.

### Faza 5 – Testy i dokumentacja
- [x] Przygotować zestaw testów jednostkowych/fake'ów dla usług i klientów.
- [x] Rozszerzyć `README.md` o instrukcje uruchomienia i konfigurację środowiska.

### Faza 6 – Dystrybucja i automatyzacja
- [x] Skonfigurować PyInstaller do budowania binariów dla Linux/Windows.
- [x] Przygotować workflow GitHub Actions publikujący binaria, sumy SHA256, ZIP źródłowy i changelog.