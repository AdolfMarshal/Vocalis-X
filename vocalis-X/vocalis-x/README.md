# Vocalis-X Backend

## Overview
This backend generates instrumental music with MusicGen and provides a scaffold
for DiffSinger-style vocal synthesis. The singing path is currently a stub that
expects you to install and configure the DiffSinger assets.

## Credits
Rena Raine voicebank and character are by **suyu**. Non-commercial use only.

## Singing Synthesis (DiffSinger) Setup
1. Install DiffSinger and required dependencies.
2. Download the Rena Raine DiffSinger 2.01 voicebank.
3. Configure the paths in the API request:
   - `singing_config.diffsinger_root`
   - `singing_config.voicebank_path`
   - `singing_config.vocoder_path`
4. Optionally provide `singing_config.melody_midi_path` (MIDI override).

## DiffSingerMiniEngine (Auto Vocals) Setup
This project supports a local DiffSingerMiniEngine server for fully automatic
lyrics -> vocals synthesis.

1. Download and extract DiffSingerMiniEngine to:
   `C:\Users\adolf\DiffSingerMiniEngine-main`
2. Copy the Rena Raine acoustic model to:
   `C:\Users\adolf\DiffSingerMiniEngine-main\assets\acoustic\rena_acoustic.onnx`
3. Ensure the vocoder is set in:
   `C:\Users\adolf\DiffSingerMiniEngine-main\configs\default.yaml`
4. Start the server:
   `python C:\Users\adolf\DiffSingerMiniEngine-main\server.py --config default`

The backend will call the MiniEngine at:
`http://127.0.0.1:9266`

## API Fields (Vocal Path)
The `/generate_with_vocals` endpoint accepts these optional fields:
- `lyrics` (string, required if vocals enabled)
- `singing_config.enabled` (bool)
- `singing_config.backend` ("diffsinger" or "external")
- `singing_config.language` ("en" or "ja")
- `singing_config.voicebank_path`
- `singing_config.diffsinger_root`
- `singing_config.vocoder_path`
- `singing_config.melody_midi_path`
- `singing_config.vocals_path` (only for backend="external")
- `singing_config.vocals_gain` (float)

## Non-Commercial Use
The DiffSinger voicebank is for non-commercial use only. Do not redistribute
voicebanks or modified versions. Always credit the creator.
