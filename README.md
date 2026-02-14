# PHP Include/Require Parentheses Rewriter

A small Python script that rewrites PHP `include()` / `include_once()` / `require()` / `require_once()` calls into the parentheses-free form.

Example:

```php
include('config.php');
require_once("init.php");
```

becomes:

```php
include 'config.php';
require_once "init.php";
```

## Safety rules (what it will and won’t change)

To avoid breaking code, the script only rewrites a line when:

- The line contains **exactly one** `include(...)` / `require(...)` statement, and
- Everything else on that line is only **whitespace** and/or **PHP comments** (`//`, `#`, `/* ... */`)

If the same line contains any other code (besides comments/whitespace), it is left unchanged.

Notes:
- The script detects comments outside of string literals.
- Multi-line block comments `/* ... */` are handled correctly across lines.

## Requirements

- Python 3.8+ (works with Python 3.14 as well)

## Usage

Run from the repository root:

```bash
python3 replace-php-includes.py
```

The script will recursively process **all `*.php` files** in the current directory and subdirectories.

### Dry run (no files changed)

```bash
python3 replace-php-includes.py --dry-run
```

### Backups

By default, the script creates a backup next to each modified file:

- `file.php` → `file.php.bak`

Backups are created **only for files that actually changed**, and only if the `.bak` file does not already exist.

Disable backups:

```bash
python3 replace-php-includes.py --no-backup
```

## Typical workflow

1. Run a dry run:
   ```bash
   python3 replace-php-includes.py --dry-run
   ```
2. Run the rewrite:
   ```bash
   python3 replace-php-includes.py
   ```
3. Review changes using your VCS (recommended):
   ```bash
   git diff
   ```

## Copyright
(c) 2026, vibecoded by utilmind


## License

MIT
