# QA i standardy deweloperskie CSM for Word

Dokument porządkuje zasady QA dla aktualnej architektury CSM for Word. Część wytycznych testera odnosiła się do innego stosu technologicznego (Gemini, React, Tailwind, `motion/react`), dlatego w CSM wdrażamy tylko elementy możliwe do potwierdzenia w tym kodzie.

## Kategorie testów

Każdy test wykonywany przez `pytest` musi należeć do jednej z kategorii:

- `current` — testy funkcjonalne aktualnie wspieranej ścieżki CSM, w szczególności trybu negocjacyjnego DOCX, instalatora, panelu Word i kontraktu frontend-backend.
- `future` — testy progresywne dokumentujące planowane lub forward-compatible zachowanie. Obecnie projekt nie zawiera aktywnych testów tej kategorii; marker jest zarezerwowany i opisany w konfiguracji.
- `regression` — testy regresyjne chroniące wcześniej naprawione błędy, zwłaszcza mechanizmy Word/Office.js, przywracanie danych, zachowanie śledzenia zmian, audyt i lokalne API.

Kategoryzacja jest wymuszana przez `tests/conftest.py`. Nowe testy mogą dostać marker jawnie, np. `@pytest.mark.current`; starsze testy są klasyfikowane po nazwach plików, aby nie rozbudowywać ich dekoratorami.

## Fail-safe i bezpieczeństwo

- Wywołania lokalnego API z panelu przechodzą przez `apiPost()`, który odróżnia błąd sieciowy od błędów HTTP i pokazuje użytkownikowi komunikat zamiast pozostawiać pusty panel.
- Backend FastAPI ma globalny handler wyjątków i sanitizuje komunikaty błędów, żeby nie ujawniać ścieżek, nazw plików ani danych liczbowych wyglądających na identyfikatory.
- Token lokalnego API jest pobierany z `CSM_API_TOKEN` albo pliku runtime generowanego przy starcie CSM. Nie wolno hardkodować sekretów w panelu ani backendzie.

## UI/UX

- Operacje dłuższe niż zwykłe kliknięcie muszą używać centralnego `setBusy()` albo przycisku spiętego przez `bindButton()`.
- W trakcie operacji panel pokazuje spinner, komunikat postępu, `aria-busy` oraz blokuje akcje, które mogłyby wejść w konflikt z trwającą pracą na dokumencie.
- Panel jest responsywny w ramach statycznego HTML/CSS używanego przez dodatek Office. Nie dodajemy Tailwind, `Loader2` ani `motion/react`, bo CSM nie jest aplikacją React.

## Definition of Done

Przed wydaniem uruchom:

```bash
npm run lint
npm run build
python -m pytest -q
```

W tej dystrybucji `npm run build` nie bundluje aplikacji. CSM jest statycznym dodatkiem Office, więc build oznacza walidację składni, obecności plików, podstawowego kontraktu UI/API i zasad bezpieczeństwa.
