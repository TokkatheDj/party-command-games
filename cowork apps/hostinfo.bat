@echo off
cd /d "%~dp0"
echo ==== HOSTNAME ==== > hostinfo.txt
hostname >> hostinfo.txt
echo ==== IP CONFIG ==== >> hostinfo.txt
ipconfig /all >> hostinfo.txt
