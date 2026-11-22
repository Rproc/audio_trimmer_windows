# Audio Trimmer (Qt + FFmpeg)

Aplicativo desktop em **Python + PySide6 (Qt 6)** para cortar (*trim*) arquivos de áudio **sem perda de qualidade**, utilizando **FFmpeg** em modo *Stream Copy* (sem recodificação), preservando metadados e capa embutida.

---

## Recursos

- **Corte sem perda de qualidade:**
  - **MP3, M4A/AAC, OGG, Opus, WMA, etc.:** corte direto via *Stream Copy* (`-c copy`), mantendo o bitstream, tags e capa do álbum (`attached_pic`).
  - **WAV / AIFF:** corte direto em PCM sem re-encode.
  - **FLAC:** corte *lossless* bit a bit (`-c:a flac`) para atualizar corretamente a duração no cabeçalho `STREAMINFO`.
- **Forma de onda interativa:**
  - Alças arrastáveis para **IN** (início) e **OUT** (fim).
  - Zoom horizontal com a roda do mouse e rolagem horizontal (`Shift + roda` ou botão do meio).
  - Edição precisa dos tempos (`MM:SS.mmm`) e botões de ajuste fino (`±0.1s`, `±1s`).
- **Player integrado (`QtMultimedia`):**
  - Reprodução completa ou apenas do trecho selecionado (com opção de **Loop**).
  - Controle de volume e cursor arrastável na forma de onda.
- **Drag & Drop:** arraste arquivos de áudio diretamente para a janela.
- **Sobrescrita segura:** grava primeiro em arquivo temporário e só substitui o destino após sucesso do FFmpeg.

---

## Atalhos de Teclado

| Atalho | Ação |
| :--- | :--- |
| `Espaço` | Tocar / Pausar |
| `I` | Marcar ponto **IN** na posição atual do cursor |
| `O` | Marcar ponto **OUT** na posição atual do cursor |
| `[` / `]` | Mover o cursor para **IN** / **OUT** |
| `Ctrl + O` | Abrir arquivo de áudio |
| `Ctrl + S` | Cortar e salvar |

---

## Pré-requisitos

- **Python 3.10+**
- **FFmpeg** e **FFprobe** disponíveis no `PATH` do sistema

---

## Instalação e Execução (a partir do código-fonte)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

No Windows, também é possível iniciar via `run.bat` (ou passar o caminho de um arquivo como argumento: `python main.py "caminho\da\musica.mp3"`).

---

## Testes Automatizados

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
```

---

## Gerar Executável Standalone (`.exe` no Windows)

```powershell
pip install pyinstaller pillow
python make_icon.py
pyinstaller --noconfirm --clean --windowed --onedir --name AudioTrimmer --icon app_icon.ico --add-data "app_icon.ico;." main.py
```

O executável será gerado em `dist\AudioTrimmer\AudioTrimmer.exe`.
