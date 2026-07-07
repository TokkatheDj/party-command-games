@echo off
cd /d "C:\Users\tokka\Claude Local\cowork apps"
echo ==== HOSTNAME ==== > hostinfo.txt
hostname >> hostinfo.txt
echo ==== IP CONFIG ==== >> hostinfo.txt
ipconfig /all >> hostinfo.txt
