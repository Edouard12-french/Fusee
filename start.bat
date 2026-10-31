@echo off
REM Lance Fusée en continu (Windows) : redémarre automatiquement en cas de plantage.
REM Pense à désactiver la mise en veille : Paramètres > Système > Alimentation > Mise en veille : Jamais.
cd /d "%~dp0"
if not exist .env (
  echo Cree d'abord le fichier .env ^(copie .env.example en .env^) et mets ta cle API.
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt
:loop
python main.py
echo Fusee s'est arretee - redemarrage dans 10 s ^(fermer la fenetre pour quitter^)
timeout /t 10 /nobreak >nul
goto loop
