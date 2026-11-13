# 12 — Open-Source, Model and Licence Governance

## 1. Core rule
A permissive code licence does not automatically cover model weights, checkpoints, training data, voices, datasets, tokenizers, phonemizers, codecs, fonts, container images, or third-party dependencies.

Never describe the entire product as open source merely because many components are open. The application may combine open-source software, open weights, third-party models, and proprietary application code.

## 2. Initial evaluation register
| Component | Blueprint observation | Required release gate |
|---|---|---|
| OpenVoice V1/V2 | Official repository states MIT and commercial/research use | Verify exact release, checkpoint, dependencies, notices |
| CosyVoice | Repository declares Apache-2.0 | Verify selected checkpoint, third-party code, assets |
| Kokoro | Model repository declares Apache-2.0 weights; language scope varies | Verify runtime, phonemizer, voice-pack terms |
| Whisper | Repository states MIT | Pin version and include notices |
| faster-whisper | Repository states MIT | Review CTranslate2 and dependency notices |
| WhisperX/diarisation | Code/model terms may differ; gated access may apply | Review each model card, access and redistribution rights |
| Ollama | Runtime and model-weight licences are distinct | Review each downloaded model card |
| FFmpeg | Build configuration affects LGPL/GPL obligations and codec patent considerations | Pin build flags and review distribution/patent exposure |
| LibreOffice/python-docx/ReportLab | Separate licences and dependencies | Include notices and verify distribution obligations |

These observations are starting points from the supplied blueprint, not a substitute for release-time legal review.

## 3. Required registers
Maintain:
- Software Bill of Materials (SBOM)
- Model registry
- Licence registry
- Dataset and voice-asset provenance register
- Source URL and exact version/checksum
- Licence text snapshot and review date
- Commercial-use approval and approver
- Redistribution obligations and notices
- Known restrictions and deployment scope

## 4. Release gate
Block release of a component if exact code, weights, assets, dependencies, or rights have not been reviewed for the intended use. Recheck at every material model or dependency update.

## 5. Official starting links
- OpenVoice: https://github.com/myshell-ai/OpenVoice
- CosyVoice: https://github.com/QwenAudio/CosyVoice
- Kokoro: https://github.com/hexgrad/kokoro
- Whisper: https://github.com/openai/whisper
- faster-whisper: https://github.com/SYSTRAN/faster-whisper
- WhisperX: https://github.com/m-bain/whisperX
- Ollama: https://ollama.com/
- FFmpeg: https://ffmpeg.org/
- Nigeria Data Protection Commission: https://ndpc.gov.ng/
