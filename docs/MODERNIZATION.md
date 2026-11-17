# Modernization Plan

Last reviewed: 2026-04-28.

## Baseline target

- Python: 3.13 as the primary runtime, with CI coverage for 3.14.
- Django: 5.2 LTS.
- PostgreSQL: 18 for Docker and CI.
- Database driver: Psycopg 3 via `psycopg[binary]`.

These choices keep the core stack on supported versions while avoiding Django
6.0 for now. Django 5.2 is the current LTS line and is a better migration
target for an old Django 3.2 application.

## Legacy ASR/NLU

The historical Snips/Kaldi implementation depended on Python 3.7/3.9 wheels
and is not part of this branch. On the original Zero W running Trixie, the
optional `install-native-asr.sh` installs PocketSphinx 5.1.1 and a French model
for clock, weather and mood commands. It uses the existing long-press capture
and native service events, independently of the Mac and Home Assistant.

The modern CI intentionally skips:

- `nabd/tests/asr_test.py`
- `nabd/tests/nlu_test.py`

Those tests should come back under a new Assist-compatible voice backend, or
under a separate legacy job that runs on the old Python/Kaldi stack.

## Non-regression strategy

1. Keep the existing daemon protocol tests and Django view tests green on the
   modern runtime.
2. Add contract tests around the Nabd TCP protocol before adding Home Assistant
   entities.
3. Add integration tests for the Assist Satellite event path before replacing
   Snips/Kaldi behavior.
4. Run PostgreSQL-backed tests in CI on every push and pull request.

## Follow-up work

- Update `install.sh` for modern Debian/Raspberry Pi OS once the target device
  OS is chosen.
- Replace the legacy ASR/NLU implementation with an Assist Satellite adapter.
- Decide whether Docker remains the primary deployment mode for development.
- Add a lockfile or generated constraints file after the dependency set is
  proven on hardware.
