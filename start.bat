@echo off
rem Double-click to start Shortsmith on Windows. It opens in your browser.
cd /d "%~dp0"

rem First start: install whichever tools are missing, through winget.
set "MISSING="
where uv >nul 2>nul || set "MISSING=%MISSING% astral-sh.uv"
where ffmpeg >nul 2>nul || set "MISSING=%MISSING% Gyan.FFmpeg"
where node >nul 2>nul || set "MISSING=%MISSING% OpenJS.NodeJS.LTS"
where pnpm >nul 2>nul || set "MISSING=%MISSING% pnpm.pnpm"
if defined MISSING (
	where winget >nul 2>nul || (
		echo Shortsmith needs winget to install its tools. Install "App Installer" from the Microsoft Store, then double-click start.bat again.
		pause
		exit /b 1
	)
	echo Installing the tools Shortsmith needs ^(first start only^)...
	for %%p in (%MISSING%) do winget install --id %%p -e --silent --accept-package-agreements --accept-source-agreements
	rem Pick up the new tools in this window, without a restart.
	for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%p"
)

rem First start: ask for the Gemini key and keep it in .env (hidden while you paste).
if not exist .env (
	echo Make a Gemini API key at https://aistudio.google.com/apikey if you do not have one yet.
	powershell -NoProfile -Command "$k = Read-Host 'Paste your Gemini API key, then press Enter' -AsSecureString; $p = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($k)); Set-Content -Path .env -Value ('GEMINI_API_KEY=' + $p) -Encoding ascii"
	echo Saved.
)

cd backend
uv run python -m app
rem Keep the window open if the app stops with an error, so the message can be read.
pause
