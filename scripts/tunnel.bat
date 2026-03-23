@echo off
REM SSH tunnel to Postgres on VPS
REM After running this, connect to localhost:15432 instead of 72.61.143.225:5432
REM Set POSTGRES_HOST=localhost and POSTGRES_PORT=15432 in .env while tunnel is open

echo Opening SSH tunnel to Postgres...
echo Connect to: localhost:15432
echo Press Ctrl+C to close tunnel

ssh -i %USERPROFILE%\.ssh\id_ed25519_hostinger -N -L 15432:localhost:5432 root@72.61.143.225
