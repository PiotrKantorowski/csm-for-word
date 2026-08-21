# CSM iter17 — instalacja, certyfikat localhost i pisma procesowe

Naprawiono problemy zgłoszone po testach na innych komputerach:

1. Instalacja nie przerywa się już z powodu ostrzeżeń pip cache, jeżeli pip kończy pracę kodem 0. Dodano `--no-cache-dir`, retry z `--force-reinstall` i weryfikację importów runtime.
2. Start CSM zawsze uruchamia weryfikator certyfikatu localhost, nawet gdy pliki `localhost.crt` i `localhost.key` już istnieją. To naprawia przypadki, w których pliki certyfikatu były obecne, ale certyfikat nie był zaufany w profilu użytkownika.
3. Komunikaty i cache-busting dodatku Word nie pokazują już `v0.5/final6` w aktywnych plikach.
4. W pismach procesowych 10-cyfrowy numer po kontekście `Faktura ... numer` nie jest już klasyfikowany jako NIP, tylko jako numer dokumentu finansowego. Numery zleceń/zamówień są maskowane jako identyfikatory sprawy/projektu.

Ograniczenia: w tym środowisku nadal nie potwierdzono testu w prawdziwym Wordzie ani działania instalatora EXE.
