@echo off
REM Display menu options
echo Welcome to the FedSystems Payments system control!
echo Please select an option:
echo 1. Generate SFTP keys
echo 2. Start all services
echo 3. Stop all services
echo 4. Stop all services and clean up Docker containers and volumes

REM Get user input
set /p option=Enter your choice (1-4):
REM Execute the selected option using simple GOTO labels (safer than nested IF parentheses)
if "%option%"=="1" goto opt1
if "%option%"=="2" goto opt2
if "%option%"=="3" goto opt3
if "%option%"=="4" goto opt4

echo Invalid option. Please run the script again and select a valid option (1-4).
pause
goto end

:opt1
echo You selected to generate SFTP keys. Running generate_keys.py...
python generate_keys.py
pause
goto end

:opt2
echo You selected to start all services. Starting Docker containers...
docker-compose up -d
pause
goto end

:opt3
echo You selected to stop all services. Stopping Docker containers...
docker-compose down
pause
goto end

:opt4
echo You selected to stop all services and clean up Docker containers and volumes. Stopping and removing Docker containers and volumes...
docker-compose down -v
pause
goto end

:end