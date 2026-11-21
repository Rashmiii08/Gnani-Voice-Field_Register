# Gnani Voice Field Register

A localhost hackathon prototype for synthetic field visits. The browser streams microphone audio to FastAPI, which uses [Prisma v3.0](https://docs.gnani.ai/api/STT/stt-websocket) and [Timbre v3.0](https://docs.gnani.ai/api/TTS/tts-websocket) over WebSocket. The live app uses local rule-based extraction and needs no separate LLM key.

## Windows live mode

Run in the VS Code PowerShell terminal that already has `GNANI_API_KEY`. From the checkout of `role-ac-integration`:

```powershell
git switch role-ac-integration
git pull --ff-only origin role-ac-integration
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not $env:GNANI_API_KEY) { throw "GNANI_API_KEY is missing in this terminal" }
$keyPath = Join-Path $env:LOCALAPPDATA "VoiceFieldRegister.data-key"
if (-not (Test-Path $keyPath)) {
    $newKey = & .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ConvertTo-SecureString $newKey -AsPlainText -Force | ConvertFrom-SecureString | Set-Content $keyPath
    Remove-Variable newKey
}
$env:DATA_KEY = [System.Net.NetworkCredential]::new("", (Get-Content $keyPath | ConvertTo-SecureString)).Password
$env:FIELD_REGISTER_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "Choose a local operator password" -AsSecureString)).Password
.\.venv\Scripts\python.exe -m uvicorn backend.live:create_live_app --factory --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765/> and sign in as `operator` using the password you just chose. If a previous simulated server is using port 8765, stop it first. Keep the app bound to localhost. The encryption key file uses Windows CurrentUser protection. Keep it to reopen records encrypted in previous sessions.

1. Start recording, allow the microphone, and wait for the AI disclosure audio.
2. Say “Routine visit. Beneficiary ID Demo one two three. Weight 55 kilograms.” Stop recording, then check the real transcript and listen to the readback.
3. In a new recording, say “Correct weight to 56 kilograms.” Stop and check the correction.
4. After hearing the updated readback, record “Yes” as its own short turn and stop. The app saves the encrypted record only after that explicit confirmation.
5. In another synthetic visit, “The newborn has a fever” exercises the fixed referral path. The demo flags limited reported symptoms based on [WHO young infant guidance](https://www.who.int/publications/i/item/9789241516365) and [WHO pregnancy warning signs](https://www.who.int/campaigns/world-health-day/2025/key-messages). It provides no diagnosis or treatment.

Use synthetic information only. A spoken ID beginning with “Demo” and a visit type are required before confirmation. A different beneficiary ID requires a new visit. Extraction recognizes explicit fields in a limited English/Hindi vocabulary, including ISO dates and named vaccines. Free-text conditions such as “has sugar” are outside the structured form.

## Check live Gnani access

In the PowerShell terminal that has `GNANI_API_KEY`, run:

```powershell
.\.venv\Scripts\python.exe -m scripts.check_gnani
```

The check asks Timbre to synthesize a fixed synthetic phrase and sends the returned audio to Prisma. It keeps the audio in memory and prints only the result. If Timbre fails, the Prisma check still attempts the connection with silence.

On failure, use the `Gnani Prisma` or `Gnani Timbre` diagnostic line. `InvalidStatus` with HTTP 401 is an upstream authentication rejection. `InvalidProxyStatus` indicates a proxy rejected the connection. `ProviderErrorFrame` indicates Gnani accepted the WebSocket upgrade and then sent an error. The diagnostic includes the phase, error class, and available numeric HTTP or close status. Header values, payloads, and close reasons are excluded.

## Simulation and tests

Simulation produces scripted transcripts and test tones without credentials.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn backend.demo:app --host 127.0.0.1 --port 8765
```

Local automated tests use synthetic data and simulated Gnani WebSocket responses. A live run requires a working Gnani credential with access to both models. Real-device latency, noise handling, and recognition accuracy require live testing.

## Delete local test records

Stop Uvicorn with Ctrl+C first. Then run:

```powershell
.\.venv\Scripts\python.exe -m scripts.delete_all_data --yes
```

The command deletes and compacts the local SQLite store. Remove any independent copies and backups separately. The app uses a single local operator account and short-lived in-memory reconnect state. The synthetic ID workflow does not verify a person's identity against a registry.
