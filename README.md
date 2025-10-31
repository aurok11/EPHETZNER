## EPhemenral Hetzner VPS Builder (EPHETZNER)

CLI tooling for provisioning and managing ephemeral Hetzner Cloud workspaces.
The CLI wraps provisioning, DuckDNS updates, optional S3 backups and clean-up
flow in a single interactive experience.

### Prerequisites

- Python 3.13+ (managed with [`uv`](https://github.com/astral-sh/uv))
- Hetzner Cloud API token
- Optional: DuckDNS token, S3-compatible credentials for backups

### Setup

```bash
uv sync --group dev      # installs runtime + developer dependencies
```

The first command run will prompt for any missing tokens. Configuration values
are resolved from the following sources (highest precedence first):

- Environment variables (`HETZNER_API_TOKEN`, `DUCKDNS_TOKEN`, `S3_ENDPOINT`,
	`S3_ACCESS_KEY`, `S3_SECRET_KEY`)
- `~/.config/ephetzner/config.ini` (or the path supplied via
	`EPHETZNER_CONFIG_PATH`). When running the packaged PyInstaller binary the
	default shifts to `./ephetzner.ini` alongside the executable.
- Interactive prompts

Whenever you complete the interactive prompts, the CLI offers to persist the
answers back to the ini file. Sensitive values are stored under the
`[ephetzner.secrets]` section with file permissions tightened to `0600`.

### Configuration

Example `~/.config/ephetzner/config.ini`:

```ini
[ephetzner]
s3_endpoint = https://objects.example

[ephetzner.secrets]
hetzner_api_token = <token>
duckdns_token = <token>
s3_access_key = <key>
s3_secret_key = <secret>
```

Generate a commented template (defaults to the active config path):

```bash
uv run python -m main config init
```

### Usage

Provision an ephemeral server:

```bash
uv run python -m main create
```

Destroy a server labelled `Type=Ephemeral` (optional backup enabled when S3
credentials are present):

```bash
uv run python -m main delete
```

Both commands may be combined with `--non-interactive` / `--server-id` flags to
streamline CI usage. DuckDNS integration is triggered automatically whenever a
token is configured.

### Backups & SSH

The delete flow can archive remote directories over SSH and push them to an
S3-compatible bucket. SSH credentials are resolved from server labels or the
following environment variables:

- `EPHETZNER_SSH_USER`
- `EPHETZNER_SSH_KEY_PATH`
- `EPHETZNER_SSH_PASSWORD`

### Packaging

PyInstaller is wired into the project for cross-platform binaries:

```bash
uv run pyinstaller --onefile --name ephetzner main.py
```

Binaries are emitted into `dist/`. The GitHub Actions release workflow builds
Linux and Windows artifacts on tag pushes (`v*`), generates SHA256 checksums,
creates a source ZIP and publishes an auto-generated changelog.

### Testing

```bash
uv run python -m unittest discover -s tests
```

The suite relies on fakes/mocks around external services and exercises the
Hetzner, DuckDNS, S3 and SSH integrations.
