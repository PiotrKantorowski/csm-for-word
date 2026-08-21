# Lokalny Bielik jako pomocniczy detektor PII

CSM moze uzyc lokalnego Bielika jako dodatkowej warstwy wykrywania elementow do anonimizacji. Silnik reglowy CSM nadal jest warstwa podstawowa, a Bielik dziala tylko po wlaczeniu.

## Co zostalo dodane

- `server/bielik_detector.py` - lokalny adapter do Ollama albo serwera OpenAI-compatible.
- `tools/start-claude-safe-mode-bielik.cmd` - start CSM z wlaczonym Bielikiem.
- `tools/setup-bielik-optional.cmd` - pomocniczy skrypt z instrukcja konfiguracji Ollama albo importu lokalnego pliku GGUF.
- Przycisk `START + BIELIK - lokalny detektor` w panelu serwisowym CSM.

## Rekomendowany start przez Ollama

1. Zainstaluj Ollama.
2. Uruchom lokalny model:

```txt
ollama run hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M
```

3. Zamknij rozmowe w terminalu albo zostaw Ollama w tle.
4. Uruchom CSM przez:

```txt
tools\start-claude-safe-mode-bielik.cmd
```

Domyslnie CSM wysyla zapytania do:

```txt
http://127.0.0.1:11434/api/chat
```

## Alternatywa: llama.cpp, LM Studio albo inny lokalny serwer

Uruchom lokalny serwer z API zgodnym z OpenAI Chat Completions i ustaw:

```txt
set CSMW_ENABLE_BIELIK=1
set CSMW_BIELIK_PROVIDER=openai
set CSMW_BIELIK_URL=http://127.0.0.1:8080/v1/chat/completions
set CSMW_BIELIK_MODEL=speakleash/Bielik-1.5B-v3.0-Instruct-GGUF
```

Potem uruchom standardowy `tools\start-claude-safe-mode.cmd`.

## Zmienne konfiguracyjne

```txt
CSMW_ENABLE_BIELIK=1
CSMW_BIELIK_PROVIDER=ollama|openai
CSMW_BIELIK_MODEL=hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M
CSMW_BIELIK_URL=http://127.0.0.1:11434/api/chat
CSMW_BIELIK_TIMEOUT_SECONDS=45
CSMW_BIELIK_CHUNK_CHARS=4500
CSMW_BIELIK_MAX_DOC_CHARS=120000
CSMW_BIELIK_MAX_CHUNKS=30
```

## Dostepne warianty modelu Bielik

Instalator CSM pozwala wybrac jeden z czterech wariantow (rosnaco wg rozmiaru i jakosci):

| Wariant | Referencja Ollama | Min. RAM | Jakosc |
|---------|-------------------|----------|--------|
| Bielik 1.5B | `hf.co/speakleash/Bielik-1.5B-v3.0-Instruct-GGUF:Q8_0` | 4 GB | podstawowa |
| Bielik 4.5B | `hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0` | 6 GB | posrednia |
| Bielik 7B Minitron (domyslny) | `hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M` | 8 GB | dobra |
| Bielik 11B | `hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M` | 12 GB | doskonala |

Bielik 4.5B (`Bielik-4.5B-v3.0-Instruct`, 4,6 mld parametrow) to model natywnie wytrenowany, dostepny w repozytorium tylko w kwantyzacji `Q8_0` (plik ~5,06 GB). Jego jakosc jest posrednia miedzy 1.5B a 7B Minitron.

## Zasady bezpieczenstwa

- CSM akceptuje od Bielika tylko fragmenty skopiowane dokladnie z dokumentu.
- CSM ignoruje odpowiedzi, ktore nie sa poprawnym JSON.
- Dane nie wychodza do internetu przez CSM; endpoint musi byc lokalny, chyba ze swiadomie ustawisz inny URL.
- Model moze sie mylic, dlatego detektor jest opcjonalny i powinien byc traktowany jako dodatkowy przeglad, a nie zamiennik kontroli czlowieka.
