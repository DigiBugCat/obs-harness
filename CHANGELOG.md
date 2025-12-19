# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Cartesia TTS Support** - Added Cartesia as an alternative TTS provider alongside ElevenLabs
  - New TTS provider abstraction layer (`src/obs_harness/tts/`) for swappable providers
  - Per-character TTS provider selection (ElevenLabs or Cartesia)
  - Provider-specific settings stored as JSON blob for flexibility
  - New API endpoints:
    - `GET /api/cartesia/models` - List available Cartesia models
    - `GET /api/cartesia/voices` - List available Cartesia voices
    - `GET /api/cartesia/voices/{voice_id}` - Get voice details
  - Dashboard UI for selecting TTS provider and configuring provider-specific settings
  - Manual voice ID entry for custom/cloned voices

### Changed
- Character model now includes `tts_provider` and `tts_settings` fields
- TTS pipeline refactored to use provider abstraction pattern
- Dashboard character form now shows provider-specific settings based on selection

### Fixed
- Cartesia speed parameter now correctly uses `generation_config.speed` (numeric 0.6-1.5) instead of deprecated `__experimental_controls`
- Added validation for empty voice IDs (must be non-empty)
- Added JSON parsing error handling for malformed `tts_settings`
- TTS settings are now validated at save time with helpful error messages
- Frontend clamps out-of-range speed values when loading characters

### Technical
- New `TTSProviderClient` protocol for unified TTS interface
- `ElevenLabsSettings` and `CartesiaSettings` Pydantic models for validation
- `create_tts_client()` factory function for provider instantiation
- `get_connect_kwargs()` extracts provider-specific connection parameters
- Backwards compatible with existing ElevenLabs-only characters

---

## Previous Releases

For changes before this changelog was created, see the git commit history.
