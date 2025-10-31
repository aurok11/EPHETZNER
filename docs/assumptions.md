# Założenia Projektu: Hetzner Ephemeral Workspaces Manager

## Opis projektu

Aplikacja CLI do zarządzania tymczasowymi workspace'ami (serwerami) w Hetzner Cloud. Umożliwia szybkie tworzenie i usuwanie serwerów z automatyczną konfiguracją oraz opcjonalnym backupem danych.

## Technologie

- **[Typer](https://typer.tiangolo.com/)** - framework do tworzenia aplikacji CLI
- **[hcloud](https://pypi.org/project/hcloud/)** - oficjalny klient Python dla Hetzner Cloud API
- **[questionary](https://pypi.org/project/questionary/)** - interaktywne menu i formularze w CLI
- **DuckDNS** - dynamiczny DNS
- **S3-compatible storage** (np. Backblaze B2) - backup danych

## Główne funkcjonalności

### 1. Tworzenie tymczasowego serwera

Funkcjonalność umożliwiająca utworzenie nowego serwera cloud w Hetzner z pełną konfiguracją.

#### 1.1. Wybór serwera

- Użytkownik wybiera serwer z interaktywnej listy (questionary)
- Lista zawiera:
  - Nazwy typów serwerów dostępnych w Hetzner Cloud
  - Parametry techniczne (CPU, RAM, dysk)
  - **Cenę za godzinę** użytkowania
- Implementacja: pobranie listy dostępnych server types z `hcloud`

#### 1.2. Wybór systemu operacyjnego

- Użytkownik wybiera system operacyjny z listy dostępnych obrazów
- Lista pobierana z Hetzner Cloud API
- Implementacja jako questionary menu

#### 1.3. Wybór projektu Hetzner

- Użytkownik wskazuje projekt Hetzner, w którym ma zostać utworzony serwer
- Może to być wybór z listy projektów lub podanie klucza API projektu

#### 1.4. Konfiguracja DuckDNS (opcjonalna)

- **Pytanie:** Czy użytkownik chce podpiąć serwer do DuckDNS?
- Jeśli TAK:
  - Pobranie wymaganych danych (token DuckDNS, subdomena)
  - Po utworzeniu serwera i otrzymaniu IP:
    - Automatyczna aktualizacja rekordu DuckDNS
    - Powiązanie subdomeny z adresem IP serwera

#### 1.5. Cloud-init script (opcjonalny)

**PRZED URUCHOMIENIEM SERWERA:**

- **Pytanie:** Czy użytkownik chce wykonać skrypt startowy?
- Jeśli TAK:
  - Wybór typu skryptu: Python lub Shell
  - Wskazanie ścieżki do skryptu (questionary File Path)
  
**Obsługa skryptu Python:**
- Sprawdzenie czy Python jest dostępny w wybranym obrazie systemu
- Jeśli Python nie jest dostępny:
  - Automatyczne dodanie instalacji Pythona do cloud-init
  - Użycie odpowiedniego menedżera pakietów (apt, yum, apk)
- Wykonanie skryptu użytkownika

**Obsługa skryptu Shell:**
- Bezpośrednie wykonanie skryptu

**Implementacja:**
- Użycie mechanizmu cloud-init w Hetzner Cloud
- Wstrzyknięcie skryptu jako user-data podczas tworzenia serwera

#### 1.6. Oznaczenie serwera (label)

Każdy utworzony serwer **MUSI** otrzymać label:

```json
{
  "Type": "Ephemeral"
}
```

Ten label służy do:
- Identyfikacji serwerów zarządzanych przez aplikację
- Filtrowania serwerów przy usuwaniu
- Odróżnienia od serwerów produkcyjnych

#### 1.7. Podsumowanie i potwierdzenie

**PRZED UTWORZENIEM SERWERA:**

Wyświetlenie podsumowania wszystkich wyborów użytkownika:

```
=== PODSUMOWANIE KONFIGURACJI ===

Typ serwera:     cx21 (2 vCPU, 4GB RAM, 40GB SSD)
Cena:            €0.006/godz (~€4.32/miesiąc)
System:          Ubuntu 22.04
Projekt:         my-hetzner-project
DuckDNS:         TAK - myserver.duckdns.org
Cloud-init:      TAK - /home/user/setup.py (Python)

==================================
```

**Opcje dla użytkownika:**
1. **Potwierdź i utwórz** - utworzenie serwera
2. **Edytuj** - powrót do menu konfiguracji (w formie menu z możliwością wyboru co zmienić)
3. **Anuluj** - przerwanie operacji

**Implementacja menu edycji:**
- Questionary select menu z opcjami do zmiany
- Po zmianie ponowne wyświetlenie podsumowania

### 2. Usuwanie tymczasowego serwera

Funkcjonalność umożliwiająca bezpieczne usunięcie serwera z opcjonalnym backupem danych.

#### 2.1. Wybór serwera do usunięcia

- Wyświetlenie listy serwerów **TYLKO** z labelem `{"Type": "Ephemeral"}`
- Lista zawiera:
  - Nazwę serwera
  - Typ serwera
  - Adres IP
  - Wiek serwera (czas od utworzenia)
  - Szacowany koszt dotychczasowego użytkowania
- Implementacja: filtrowanie serwerów po labelach w `hcloud`

#### 2.2. Opcjonalny backup do S3

**PRZED USUNIĘCIEM SERWERA:**

- **Pytanie:** Czy użytkownik chce wykonać backup plików?
- Jeśli TAK:
  1. **Wskazanie ścieżki do backupu** (questionary File Path lub Path input)
     - Użytkownik podaje ścieżkę na serwerze, którą chce zbackupować
     - Może to być folder lub pojedynczy plik
  
  2. **Konfiguracja S3 storage:**
     - Endpoint URL (np. s3.us-west-002.backblazeb2.com)
     - Bucket name
     - Access Key ID
     - Secret Access Key
     - Opcjonalnie: prefix/ścieżka w bucket
  
  3. **Proces backupu:**
     - Połączenie SSH z serwerem
     - Spakowanie wskazanej ścieżki (tar.gz)
     - Upload do S3-compatible storage
     - **Weryfikacja:** sprawdzenie czy plik został pomyślnie przesłany
       - Porównanie checksum (MD5/SHA256)
       - Potwierdzenie istnienia pliku w bucket
  
  4. **Usunięcie serwera:**
     - Następuje **DOPIERO PO** pomyślnej weryfikacji backupu
     - W przypadku błędu backupu - pyta czy usunąć mimo to

#### 2.3. Podsumowanie przed usunięciem

Wyświetlenie podsumowania:

```
=== PODSUMOWANIE USUNIĘCIA ===

Serwer:          my-workspace-01
Typ:             cx21
Adres IP:        123.45.67.89
Czas działania:  3 dni, 5 godzin
Całkowity koszt: ~€0.43

Backup:          TAK
Ścieżka:         /home/user/project
Destination:     s3://my-bucket/backups/my-workspace-01/

==============================
```

**Pytanie o potwierdzenie:**
- TAK - wykonaj backup (jeśli wybrano) i usuń serwer
- NIE - anuluj operację

#### 2.4. Status operacji

Po potwierdzeniu wyświetlanie statusu w czasie rzeczywistym:

```
[1/4] Łączenie z serwerem... ✓
[2/4] Pakowanie danych... ✓
[3/4] Upload do S3... ████████████ 100% ✓
[4/4] Weryfikacja backupu... ✓
[5/5] Usuwanie serwera... ✓

Serwer został pomyślnie usunięty!
Backup dostępny: s3://my-bucket/backups/my-workspace-01/backup-2025-10-30.tar.gz
```

## Wymagania techniczne

### Wymagane biblioteki

```
typer>=0.9.0
hcloud>=1.33.0
questionary>=2.0.0
boto3>=1.28.0  # dla S3-compatible storage
paramiko>=3.3.0  # dla SSH (backup)
rich>=13.0.0  # dla ładnego formatowania output
```

### Zmienne środowiskowe

```bash
HETZNER_API_TOKEN=your_token_here
DUCKDNS_TOKEN=your_token_here  # opcjonalnie
S3_ENDPOINT=s3.us-west-002.backblazeb2.com  # opcjonalnie
S3_ACCESS_KEY=your_key_here  # opcjonalnie
S3_SECRET_KEY=your_secret_here  # opcjonalnie
```

### Struktura projektu

```
hetzner-ephemeral-manager/
├── main.py                 # Punkt wejścia aplikacji (Typer)
├── commands/
│   ├── __init__.py
│   ├── create.py          # Komenda tworzenia serwera
│   └── delete.py          # Komenda usuwania serwera
├── services/
│   ├── __init__.py
│   ├── hetzner.py         # Obsługa Hetzner Cloud API
│   ├── duckdns.py         # Integracja z DuckDNS
│   ├── s3.py              # Obsługa S3 backup
│   └── ssh.py             # Obsługa połączeń SSH
├── ui/
│   ├── __init__.py
│   ├── menus.py           # Definicje menu questionary
│   └── formatters.py      # Formatowanie output
├── config.py              # Konfiguracja i zmienne środowiskowe
├── requirements.txt
└── README.md
```

## Przykładowe użycie

### Tworzenie serwera

```bash
# Interaktywne menu
python main.py create

# Z parametrami (opcjonalnie)
python main.py create --server-type cx21 --image ubuntu-22.04
```

### Usuwanie serwera

```bash
# Interaktywne menu
python main.py delete

# Z parametrami (opcjonalnie)
python main.py delete --server-name my-workspace --backup /home/user/data
```

## Uwagi implementacyjne

### Bezpieczeństwo

- **Tokeny i klucze API** nigdy nie są hardcodowane
- Używanie zmiennych środowiskowych lub bezpiecznego storage (keyring)
- Połączenia SSH z weryfikacją kluczy
- Szyfrowane połączenia z S3

### Obsługa błędów

- Graceful degradation przy problemach z API
- Czytelne komunikaty błędów dla użytkownika
- Rollback w przypadku błędu podczas tworzenia serwera
- Logowanie błędów do pliku

### User Experience

- Progress bar dla długotrwałych operacji
- Kolorowe output (rich/questionary)
- Możliwość przerwania operacji (Ctrl+C)
- Walidacja inputów użytkownika
- Podpowiedzi i help text

### Performance

- Cache dla list serwerów/obrazów
- Async operacje gdzie to możliwe
- Timeout dla operacji sieciowych

## Roadmap / Przyszłe funkcjonalności

- [ ] Lista wszystkich ephemeral serwerów z podsumowaniem kosztów
- [ ] Automatyczne usuwanie serwerów po określonym czasie
- [ ] Szablony konfiguracji (zapisywanie i wczytywanie)
- [ ] Integracja z innymi providerami cloud (AWS, DigitalOcean)
- [ ] Web UI jako alternatywa dla CLI
- [ ] Monitoring kosztów i alerty
- [ ] Snapshoty serwerów przed usunięciem
- [ ] Automatyczne backupy co X godzin

## Licencja

MIT

## Autor

[Twoje imię/nick]
